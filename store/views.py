# =========================================================
# views.py
# =========================================================

from decimal import Decimal
import base64
import hashlib
import hmac
import json
import time

import requests

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import (
    authenticate,
    login,
    logout,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from .models import (
    Category,
    Product,
    ProductSpecificationGroup,
    ProductReview,
    CustomerProfile,
    CartItem,
    Order,
    OrderItem,
    Notification,
    Wishlist,
)


# =========================================================
# HELPERS
# =========================================================

def get_safe_next_url(request, default="home"):
    """
    Get a safe redirect URL from GET/POST.
    Prevents open redirect attacks.
    """

    next_url = (
        request.POST.get("next")
        or request.GET.get("next")
    )

    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url

    return default


def get_cart_items(user):
    """
    Return user's cart items.
    """

    if not user.is_authenticated:
        return CartItem.objects.none()

    return (
        CartItem.objects
        .filter(user=user)
        .select_related(
            "product",
            "product__category",
        )
        .order_by("-id")
    )


def get_cart_count(user):
    """
    Return total quantity of products in cart.
    """

    if not user.is_authenticated:
        return 0

    return sum(
        item.quantity
        for item in CartItem.objects.filter(user=user)
    )


def get_cart_total(user):
    """
    Return total cart price.
    """

    if not user.is_authenticated:
        return Decimal("0.00")

    total = Decimal("0.00")

    items = (
        CartItem.objects
        .filter(user=user)
        .select_related("product")
    )

    for item in items:
        total += (
            item.product.price
            * item.quantity
        )

    return total


def get_wishlist_items(user):
    """
    Return user's wishlist.
    """

    if not user.is_authenticated:
        return Wishlist.objects.none()

    return (
        Wishlist.objects
        .filter(user=user)
        .select_related(
            "product",
            "product__category",
        )
        .order_by("-created_at")
    )


def get_wishlist_count(user):
    """
    Return wishlist item count.
    """

    if not user.is_authenticated:
        return 0

    return Wishlist.objects.filter(
        user=user
    ).count()


def get_unread_notification_count(user):
    """
    Return unread notification count.
    """

    if not user.is_authenticated:
        return 0

    return Notification.objects.filter(
        user=user,
        is_read=False,
    ).count()


def build_common_context(request):
    """
    Common context used by most pages.
    """

    if not request.user.is_authenticated:
        return {
            "cart_items": [],
            "cart_count": 0,
            "cart_total": Decimal("0.00"),
            "wishlist_items": [],
            "wishlist_count": 0,
            "unread_notification_count": 0,
        }

    return {
        "cart_items": get_cart_items(request.user),
        "cart_count": get_cart_count(request.user),
        "cart_total": get_cart_total(request.user),
        "wishlist_items": get_wishlist_items(request.user),
        "wishlist_count": get_wishlist_count(request.user),
        "unread_notification_count": (
            get_unread_notification_count(
                request.user
            )
        ),
    }


def get_checkout_context(
    request,
    cart_items,
    cart_count,
    subtotal,
    delivery,
    tax,
    total,
    profile_obj,
):
    """
    Common checkout context.
    """

    context = {
        "cart_items": cart_items,
        "cart_count": cart_count,
        "cart_total": subtotal,
        "subtotal": subtotal,
        "delivery": delivery,
        "tax": tax,
        "total": total,
        "profile": profile_obj,
    }

    context.update(
        build_common_context(request)
    )

    return context


# =========================================================
# ESEWA HELPERS
# =========================================================

def get_esewa_settings():
    """
    Get eSewa configuration from Django settings.

    Add these to settings.py:

        ESEWA_PAYMENT_URL = (
            "https://rc-epay.esewa.com.np/"
            "api/epay/main/v2/form"
        )

        ESEWA_STATUS_URL = (
            "https://rc-epay.esewa.com.np/"
            "api/epay/transaction/status/"
        )

        ESEWA_PRODUCT_CODE = "EPAYTEST"

        ESEWA_SECRET_KEY = "8gBm/:&EnhH.1/q"

    For production, change the URLs and credentials.
    """

    return {
        "payment_url": getattr(
            settings,
            "ESEWA_PAYMENT_URL",
            (
                "https://rc-epay.esewa.com.np/"
                "api/epay/main/v2/form"
            ),
        ),
        "status_url": getattr(
            settings,
            "ESEWA_STATUS_URL",
            (
                "https://rc-epay.esewa.com.np/"
                "api/epay/transaction/status/"
            ),
        ),
        "product_code": getattr(
            settings,
            "ESEWA_PRODUCT_CODE",
            "EPAYTEST",
        ),
        "secret_key": getattr(
            settings,
            "ESEWA_SECRET_KEY",
            "8gBm/:&EnhH.1/q",
        ),
    }


def generate_esewa_signature(
    total_amount,
    transaction_uuid,
    product_code,
    secret_key,
):
    """
    Generate HMAC SHA-256 signature required by eSewa.
    """

    message = (
        f"total_amount={total_amount},"
        f"transaction_uuid={transaction_uuid},"
        f"product_code={product_code}"
    )

    signature = base64.b64encode(
        hmac.new(
            secret_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).digest()
    ).decode("utf-8")

    return signature


def verify_esewa_signature(data, secret_key):
    """
    Verify eSewa success response signature.

    eSewa sends an encoded JSON response containing:
        status
        total_amount
        transaction_uuid
        product_code
        signed_field_names
        signature
        transaction_code
    """

    received_signature = data.get("signature")

    if not received_signature:
        return False

    signed_field_names = data.get(
        "signed_field_names",
        "",
    )

    if not signed_field_names:
        return False

    fields = signed_field_names.split(",")

    message_parts = []

    for field in fields:
        if field not in data:
            return False

        message_parts.append(
            f"{field}={data[field]}"
        )

    message = ",".join(message_parts)

    expected_signature = base64.b64encode(
        hmac.new(
            secret_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).digest()
    ).decode("utf-8")

    return hmac.compare_digest(
        received_signature,
        expected_signature,
    )


def decode_esewa_response(encoded_data):
    """
    Decode eSewa Base64 JSON response.
    """

    try:
        decoded = base64.b64decode(
            encoded_data
        ).decode("utf-8")

        return json.loads(decoded)

    except (
        ValueError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        base64.binascii.Error,
    ):
        return None


def verify_esewa_transaction(
    transaction_uuid,
    total_amount,
    product_code,
):
    """
    Verify transaction directly with eSewa.

    Returns:
        dict response if successful request
        None if verification request fails
    """

    esewa = get_esewa_settings()

    try:
        response = requests.get(
            esewa["status_url"],
            params={
                "product_code": product_code,
                "total_amount": str(total_amount),
                "transaction_uuid": transaction_uuid,
            },
            timeout=15,
        )

        if response.status_code != 200:
            return None

        return response.json()

    except (
        requests.RequestException,
        ValueError,
    ):
        return None


# =========================================================
# HOME
# =========================================================

def home(request):

    products = (
        Product.objects
        .select_related("category")
        .order_by("-created_at")
    )

    categories = Category.objects.all()

    context = {
        "products": products,
        "categories": categories,
    }

    context.update(
        build_common_context(request)
    )

    return render(
        request,
        "home.html",
        context,
    )


# =========================================================
# PRODUCTS
# =========================================================

def products(request):

    product_list = (
        Product.objects
        .select_related("category")
        .order_by("-created_at")
    )

    query = request.GET.get(
        "q",
        "",
    ).strip()

    category_slug = request.GET.get(
        "category",
        "",
    ).strip()

    if query:
        product_list = product_list.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(category__name__icontains=query)
        )

    selected_category = None

    if category_slug:

        selected_category = get_object_or_404(
            Category,
            slug=category_slug,
        )

        product_list = product_list.filter(
            category=selected_category
        )

    context = {
        "products": product_list,
        "categories": Category.objects.all(),
        "query": query,
        "selected_category": selected_category,
    }

    context.update(
        build_common_context(request)
    )

    return render(
        request,
        "products.html",
        context,
    )


# =========================================================
# CATEGORY PRODUCTS
# =========================================================

def category_products(request, category_name):

    category = get_object_or_404(
        Category,
        slug=category_name,
    )

    product_list = (
        Product.objects
        .filter(category=category)
        .select_related("category")
        .order_by("-created_at")
    )

    context = {
        "category": category,
        "products": product_list,
        "categories": Category.objects.all(),
        "query": "",
        "selected_category": category,
    }

    context.update(
        build_common_context(request)
    )

    return render(
        request,
        "products.html",
        context,
    )


# =========================================================
# PRODUCT DETAIL
# =========================================================

def product_detail(request, id):

    product = get_object_or_404(
        Product.objects.select_related("category"),
        id=id,
    )

    # -----------------------------------------------------
    # SPECIFICATIONS
    # -----------------------------------------------------

    specification_groups = (
        ProductSpecificationGroup.objects
        .filter(product=product)
        .prefetch_related("specifications")
        .order_by(
            "display_order",
            "id",
        )
    )

    # -----------------------------------------------------
    # REVIEWS
    # -----------------------------------------------------

    reviews = (
        ProductReview.objects
        .filter(product=product)
        .select_related("user")
        .order_by("-created_at")
    )

    # -----------------------------------------------------
    # REVIEW STATISTICS
    # -----------------------------------------------------

    review_stats = reviews.aggregate(
        average_rating=Avg("rating"),
        review_count=Count("id"),
    )

    average_rating = (
        review_stats["average_rating"]
        or 0
    )

    review_count = (
        review_stats["review_count"]
        or 0
    )

    # -----------------------------------------------------
    # RATING BREAKDOWN
    # -----------------------------------------------------

    rating_rows = []

    for rating in range(5, 0, -1):

        count = reviews.filter(
            rating=rating
        ).count()

        if review_count > 0:
            percent = round(
                (count / review_count) * 100
            )
        else:
            percent = 0

        rating_rows.append({
            "rating": rating,
            "count": count,
            "percent": percent,
        })

    # -----------------------------------------------------
    # CURRENT USER REVIEW
    # -----------------------------------------------------

    user_review = None

    if request.user.is_authenticated:

        user_review = (
            ProductReview.objects
            .filter(
                product=product,
                user=request.user,
            )
            .first()
        )

    # -----------------------------------------------------
    # SIMILAR PRODUCTS
    # -----------------------------------------------------

    similar_products = (
        Product.objects
        .filter(
            category=product.category
        )
        .exclude(
            id=product.id
        )
        .select_related("category")
        .order_by("-id")[:4]
    )

    # -----------------------------------------------------
    # CONTEXT
    # -----------------------------------------------------

    context = {
        "product": product,

        "specification_groups": (
            specification_groups
        ),

        "spec_groups": specification_groups,

        "reviews": reviews,

        "average_rating": round(
            float(average_rating),
            1,
        ),

        "review_count": review_count,

        "user_review": user_review,

        "rating_rows": rating_rows,

        "similar_products": similar_products,
    }

    context.update(
        build_common_context(request)
    )

    return render(
        request,
        "product_detail.html",
        context,
    )


# =========================================================
# ADD TO CART
# =========================================================

@login_required
@require_POST
def add_to_cart(request, id):

    try:
        requested_quantity = int(
            request.POST.get(
                "quantity",
                1,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        requested_quantity = 1

    requested_quantity = max(
        requested_quantity,
        1,
    )

    with transaction.atomic():

        product = (
            Product.objects
            .select_for_update()
            .get(id=id)
        )

        # -------------------------------------------------
        # CHECK STOCK
        # -------------------------------------------------

        if product.stock <= 0:

            messages.warning(
                request,
                f"{product.name} is out of stock.",
            )

            return redirect(
                "product_detail",
                id=product.id,
            )

        # -------------------------------------------------
        # FIND EXISTING CART ITEM
        # -------------------------------------------------

        item = (
            CartItem.objects
            .select_for_update()
            .filter(
                user=request.user,
                product=product,
            )
            .first()
        )

        # -------------------------------------------------
        # PRODUCT ALREADY IN CART
        # -------------------------------------------------

        if item:

            new_quantity = (
                item.quantity
                + requested_quantity
            )

            if new_quantity > product.stock:

                new_quantity = product.stock

                item.quantity = new_quantity

                item.save(
                    update_fields=[
                        "quantity"
                    ]
                )

                messages.warning(
                    request,
                    f"Only {product.stock} of "
                    f"{product.name} are available.",
                )

            else:

                item.quantity = new_quantity

                item.save(
                    update_fields=[
                        "quantity"
                    ]
                )

                messages.success(
                    request,
                    f"{product.name} quantity updated in your cart.",
                )

        # -------------------------------------------------
        # NEW CART ITEM
        # -------------------------------------------------

        else:

            quantity = min(
                requested_quantity,
                product.stock,
            )

            CartItem.objects.create(
                user=request.user,
                product=product,
                quantity=quantity,
            )

            if requested_quantity > product.stock:

                messages.warning(
                    request,
                    f"Only {product.stock} of "
                    f"{product.name} are available.",
                )

            else:

                messages.success(
                    request,
                    f"{product.name} was added to your cart.",
                )

    # -----------------------------------------------------
    # STAY ON PRODUCT DETAIL PAGE
    # -----------------------------------------------------

    return redirect(
        "product_detail",
        id=product.id,
    )


# =========================================================
# CART
# =========================================================

@login_required
def cart(request):

    cart_items = list(
        CartItem.objects
        .filter(user=request.user)
        .select_related(
            "product",
            "product__category",
        )
        .order_by("-id")
    )

    cart_count = 0
    cart_total = Decimal("0.00")

    items_to_delete = []
    items_to_update = []

    for item in cart_items:

        if item.quantity < 1:
            item.quantity = 1
            items_to_update.append(item)

        if item.product.stock <= 0:
            items_to_delete.append(item)
            continue

        if item.quantity > item.product.stock:
            item.quantity = item.product.stock
            items_to_update.append(item)

        cart_count += item.quantity

        cart_total += (
            item.product.price
            * item.quantity
        )

    if items_to_update:

        for item in items_to_update:
            item.save(
                update_fields=["quantity"]
            )

    if items_to_delete:

        CartItem.objects.filter(
            id__in=[
                item.id
                for item in items_to_delete
            ],
            user=request.user,
        ).delete()

        cart_items = [
            item
            for item in cart_items
            if item not in items_to_delete
        ]

    context = {
        "cart_items": cart_items,
        "cart_count": cart_count,
        "cart_total": cart_total,
    }

    context.update(
        build_common_context(request)
    )

    return render(
        request,
        "cart.html",
        context,
    )


# =========================================================
# INCREASE QUANTITY
# =========================================================

@login_required
@require_POST
def increase_quantity(request, id):

    with transaction.atomic():

        item = get_object_or_404(
            CartItem.objects
            .select_for_update()
            .select_related("product"),
            product_id=id,
            user=request.user,
        )

        product = (
            Product.objects
            .select_for_update()
            .get(id=item.product.id)
        )

        if product.stock <= 0:

            product_name = product.name

            item.delete()

            messages.warning(
                request,
                f"{product_name} is out of stock.",
            )

            return redirect("cart")

        if item.quantity >= product.stock:

            messages.warning(
                request,
                f"Only {product.stock} of "
                f"{product.name} are available.",
            )

            return redirect("cart")

        item.quantity += 1

        item.save(
            update_fields=["quantity"]
        )

    messages.success(
        request,
        f"{product.name} quantity increased.",
    )

    return redirect("cart")


# =========================================================
# DECREASE QUANTITY
# =========================================================

@login_required
@require_POST
def decrease_quantity(request, id):

    with transaction.atomic():

        item = get_object_or_404(
            CartItem.objects
            .select_for_update()
            .select_related("product"),
            product_id=id,
            user=request.user,
        )

        product_name = item.product.name

        if item.quantity <= 1:

            item.delete()

            messages.success(
                request,
                f"{product_name} was removed from your cart.",
            )

            return redirect("cart")

        item.quantity -= 1

        item.save(
            update_fields=["quantity"]
        )

    messages.success(
        request,
        f"{product_name} quantity decreased.",
    )

    return redirect("cart")


# =========================================================
# UPDATE QUANTITY
# =========================================================

@login_required
@require_POST
def update_quantity(request, id):

    item = get_object_or_404(
        CartItem.objects
        .select_related("product"),
        product_id=id,
        user=request.user,
    )

    product = item.product
    product_name = product.name

    quantity_value = request.POST.get(
        "quantity"
    )

    try:

        quantity = int(
            quantity_value or 1
        )

    except (
        TypeError,
        ValueError,
    ):

        messages.error(
            request,
            "Invalid quantity.",
        )

        return redirect("cart")

    if quantity <= 0:

        item.delete()

        messages.success(
            request,
            f"{product_name} was removed from your cart.",
        )

        return redirect("cart")

    with transaction.atomic():

        product = (
            Product.objects
            .select_for_update()
            .get(id=product.id)
        )

        item = (
            CartItem.objects
            .select_for_update()
            .get(
                id=item.id,
                user=request.user,
            )
        )

        if product.stock <= 0:

            item.delete()

            messages.warning(
                request,
                f"{product_name} is out of stock.",
            )

            return redirect("cart")

        if quantity > product.stock:

            quantity = product.stock

            messages.warning(
                request,
                f"Only {product.stock} of "
                f"{product_name} are available.",
            )

        item.quantity = quantity

        item.save(
            update_fields=["quantity"]
        )

    return redirect("cart")


# =========================================================
# REMOVE FROM CART
# =========================================================

@login_required
@require_POST
def remove_from_cart(request, id):

    item = get_object_or_404(
        CartItem,
        product_id=id,
        user=request.user,
    )

    product_name = item.product.name

    item.delete()

    messages.success(
        request,
        f"{product_name} was removed from your cart.",
    )

    return redirect("cart")


# =========================================================
# WISHLIST
# =========================================================

@login_required
def wishlist(request):

    items = list(
        get_wishlist_items(
            request.user
        )
    )

    context = {
        "items": items,
        "wishlist_items": items,
        "wishlist_count": len(items),
    }

    context.update(
        build_common_context(request)
    )

    return render(
        request,
        "wishlist.html",
        context,
    )


# =========================================================
# ADD WISHLIST
# =========================================================

@login_required
@require_POST
def add_wishlist(request, id):

    product = get_object_or_404(
        Product,
        id=id,
    )

    wishlist_item, created = (
        Wishlist.objects.get_or_create(
            user=request.user,
            product=product,
        )
    )

    if created:

        messages.success(
            request,
            f"{product.name} was added to your wishlist.",
        )

    else:

        messages.info(
            request,
            f"{product.name} is already in your wishlist.",
        )

    return redirect(
        get_safe_next_url(
            request,
            "wishlist",
        )
    )


# =========================================================
# REMOVE WISHLIST
# =========================================================

@login_required
@require_POST
def remove_wishlist(request, id):

    product = get_object_or_404(
        Product,
        id=id,
    )

    Wishlist.objects.filter(
        user=request.user,
        product=product,
    ).delete()

    messages.success(
        request,
        f"{product.name} was removed from your wishlist.",
    )

    return redirect(
        get_safe_next_url(
            request,
            "wishlist",
        )
    )


# =========================================================
# ADD / UPDATE REVIEW
# =========================================================
# =========================================================
# ADD / UPDATE REVIEW
# ONLY CUSTOMERS CAN SUBMIT REVIEWS
# =========================================================

@login_required
@require_POST
def add_review(request, id):

    product = get_object_or_404(
        Product,
        id=id,
    )

    # -----------------------------------------------------
    # PREVENT ADMIN / STAFF FROM POSTING REVIEWS
    # -----------------------------------------------------

    if request.user.is_staff or request.user.is_superuser:

        messages.error(
            request,
            "Only customers can submit product reviews.",
        )

        return redirect(
            "product_detail",
            id=product.id,
        )

    # -----------------------------------------------------
    # RATING
    # -----------------------------------------------------

    try:

        rating = int(
            request.POST.get(
                "rating",
                5,
            )
        )

    except (
        TypeError,
        ValueError,
    ):

        messages.error(
            request,
            "Invalid rating.",
        )

        return redirect(
            "product_detail",
            id=product.id,
        )

    if rating < 1 or rating > 5:

        messages.error(
            request,
            "Rating must be between 1 and 5.",
        )

        return redirect(
            "product_detail",
            id=product.id,
        )

    # -----------------------------------------------------
    # REVIEW CONTENT
    # -----------------------------------------------------

    title = request.POST.get(
        "title",
        "",
    ).strip()

    comment = request.POST.get(
        "comment",
        "",
    ).strip()

    if not comment:

        messages.error(
            request,
            "Please write a review before submitting.",
        )

        return redirect(
            "product_detail",
            id=product.id,
        )

    # -----------------------------------------------------
    # CREATE / UPDATE REVIEW
    # -----------------------------------------------------

    review, created = (
        ProductReview.objects.update_or_create(
            product=product,
            user=request.user,
            defaults={
                "rating": rating,
                "title": title,
                "comment": comment,
            },
        )
    )

    # -----------------------------------------------------
    # SUCCESS MESSAGE
    # -----------------------------------------------------

    if created:

        messages.success(
            request,
            "Your review was added.",
        )

    else:

        messages.success(
            request,
            "Your review was updated.",
        )

    return redirect(
        "product_detail",
        id=product.id,
    )


# =========================================================
# DELETE REVIEW
# ONLY THE CUSTOMER'S OWN REVIEW CAN BE DELETED
# =========================================================

@login_required
@require_POST
def delete_review(request, id):

    product = get_object_or_404(
        Product,
        id=id,
    )

    deleted_count, _ = (
        ProductReview.objects
        .filter(
            product=product,
            user=request.user,
        )
        .delete()
    )

    if deleted_count:

        messages.success(
            request,
            "Your review was deleted.",
        )

    else:

        messages.error(
            request,
            "You do not have a review for this product.",
        )

    return redirect(
        "product_detail",
        id=product.id,
    )


# =========================================================
# LOGIN
# =========================================================

def login_view(request):

    if request.user.is_authenticated:
        return redirect("home")

    next_url = (
        request.POST.get("next")
        or request.GET.get("next")
    )

    if request.method == "POST":

        username = request.POST.get(
            "username",
            "",
        ).strip()

        password = request.POST.get(
            "password",
            "",
        )

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is not None:

            login(
                request,
                user,
            )

            messages.success(
                request,
                "Welcome back!",
            )

            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):

                return redirect(
                    next_url
                )

            return redirect("home")

        messages.error(
            request,
            "Invalid username or password.",
        )

    return render(
        request,
        "login.html",
        {
            "next": next_url or "",
        },
    )


# =========================================================
# LOGOUT
# =========================================================

@login_required
def logout_view(request):

    logout(request)

    messages.success(
        request,
        "You have been logged out.",
    )

    return redirect("home")


# =========================================================
# REGISTER
# =========================================================

def register(request):

    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":

        username = request.POST.get(
            "username",
            "",
        ).strip()

        email = request.POST.get(
            "email",
            "",
        ).strip()

        password = request.POST.get(
            "password",
            "",
        )

        confirm_password = request.POST.get(
            "confirm_password",
            "",
        )

        first_name = request.POST.get(
            "first_name",
            "",
        ).strip()

        last_name = request.POST.get(
            "last_name",
            "",
        ).strip()

        phone = request.POST.get(
            "phone",
            "",
        ).strip()

        middle_name = request.POST.get(
            "middle_name",
            "",
        ).strip()

        address = request.POST.get(
            "address",
            "",
        ).strip()

        if not username or not email or not password:

            messages.error(
                request,
                "Please fill in all required fields.",
            )

            return render(
                request,
                "register.html",
            )

        try:

            validate_email(email)

        except ValidationError:

            messages.error(
                request,
                "Please enter a valid email address.",
            )

            return render(
                request,
                "register.html",
            )

        if password != confirm_password:

            messages.error(
                request,
                "Passwords do not match.",
            )

            return render(
                request,
                "register.html",
            )

        if User.objects.filter(
            username__iexact=username
        ).exists():

            messages.error(
                request,
                "That username is already taken.",
            )

            return render(
                request,
                "register.html",
            )

        if User.objects.filter(
            email__iexact=email
        ).exists():

            messages.error(
                request,
                "An account with that email already exists.",
            )

            return render(
                request,
                "register.html",
            )

        with transaction.atomic():

            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )

            CustomerProfile.objects.create(
                user=user,
                middle_name=middle_name,
                phone=phone,
                address=address,
            )

        login(
            request,
            user,
        )

        messages.success(
            request,
            "Your account has been created.",
        )

        return redirect("home")

    return render(
        request,
        "register.html",
    )


# =========================================================
# PROFILE
# =========================================================

@login_required
def profile(request):

    profile_obj, created = (
        CustomerProfile.objects.get_or_create(
            user=request.user,
            defaults={
                "phone": "",
            },
        )
    )

    if request.method == "POST":

        email = request.POST.get(
            "email",
            "",
        ).strip()

        if email:

            try:

                validate_email(email)

            except ValidationError:

                messages.error(
                    request,
                    "Please enter a valid email address.",
                )

                return redirect("profile")

            email_exists = (
                User.objects
                .filter(email__iexact=email)
                .exclude(id=request.user.id)
                .exists()
            )

            if email_exists:

                messages.error(
                    request,
                    "That email address is already in use.",
                )

                return redirect("profile")

        request.user.first_name = request.POST.get(
            "first_name",
            "",
        ).strip()

        request.user.last_name = request.POST.get(
            "last_name",
            "",
        ).strip()

        request.user.email = email

        request.user.save(
            update_fields=[
                "first_name",
                "last_name",
                "email",
            ]
        )

        profile_obj.middle_name = request.POST.get(
            "middle_name",
            "",
        ).strip()

        profile_obj.phone = request.POST.get(
            "phone",
            "",
        ).strip()

        profile_obj.address = request.POST.get(
            "address",
            "",
        ).strip()

        profile_obj.save()

        messages.success(
            request,
            "Your profile has been updated.",
        )

        return redirect("profile")

    orders = (
        Order.objects
        .filter(user=request.user)
        .prefetch_related("items__product")
        .order_by("-created_at")
    )

    context = {
        "profile": profile_obj,
        "orders": orders,
    }

    context.update(
        build_common_context(request)
    )

    return render(
        request,
        "profile.html",
        context,
    )


# =========================================================
# CUSTOMER CHANGE PASSWORD
# =========================================================

@login_required
def change_password(request):
    """
    Allow logged-in customers to change their own password.

    Django's PasswordChangeForm:
    - Checks the current password.
    - Validates the new password.
    - Hashes the new password correctly.
    - Prevents invalid password changes.

    update_session_auth_hash() keeps the customer
    logged in after changing their password.
    """

    if request.method == "POST":

        form = PasswordChangeForm(
            user=request.user,
            data=request.POST,
        )

        if form.is_valid():

            user = form.save()

            # Keep the customer logged in after
            # changing their password.
            update_session_auth_hash(
                request,
                user,
            )

            messages.success(
                request,
                "Your password has been changed successfully.",
            )

            return redirect("profile")

        messages.error(
            request,
            "Please correct the errors below.",

        )

    else:

        form = PasswordChangeForm(
            user=request.user,
        )

    context = {
        "form": form,
    }

    context.update(
        build_common_context(request)
    )

    return render(
        request,
        "change_password.html",
        context,
    )


# =========================================================
# CHECKOUT
# =========================================================

@login_required
def checkout(request):

    cart_items = list(
        CartItem.objects
        .filter(user=request.user)
        .select_related(
            "product",
            "product__category",
        )
        .order_by("-id")
    )

    if not cart_items:

        messages.info(
            request,
            "Your cart is empty.",
        )

        return redirect("cart")

    # -----------------------------------------------------
    # CHECK STOCK
    # -----------------------------------------------------

    for item in cart_items:

        if item.quantity < 1:

            item.quantity = 1

            item.save(
                update_fields=["quantity"]
            )

        if item.product.stock <= 0:

            messages.error(
                request,
                f"{item.product.name} is out of stock.",
            )

            return redirect("cart")

        if item.quantity > item.product.stock:

            messages.error(
                request,
                f"Only {item.product.stock} of "
                f"{item.product.name} are available.",
            )

            return redirect("cart")

    # -----------------------------------------------------
    # CALCULATE TOTAL
    # -----------------------------------------------------

    cart_count = sum(
        item.quantity
        for item in cart_items
    )

    subtotal = sum(
        (
            item.product.price
            * item.quantity
            for item in cart_items
        ),
        Decimal("0.00"),
    )

    delivery = Decimal("0.00")
    tax = Decimal("0.00")

    total = (
        subtotal
        + delivery
        + tax
    )

    # -----------------------------------------------------
    # CUSTOMER PROFILE
    # -----------------------------------------------------

    profile_obj = (
        CustomerProfile.objects
        .filter(user=request.user)
        .first()
    )

    # =====================================================
    # POST
    # =====================================================

    if request.method == "POST":

        full_name = request.POST.get(
            "full_name",
            "",
        ).strip()

        email = request.POST.get(
            "email",
            "",
        ).strip()

        phone = request.POST.get(
            "phone",
            "",
        ).strip()

        address = request.POST.get(
            "address",
            "",
        ).strip()

        city = request.POST.get(
            "city",
            "",
        ).strip()

        payment_method = request.POST.get(
            "payment_method",
            "COD",
        ).upper()

        # -------------------------------------------------
        # PAYMENT METHOD
        # -------------------------------------------------

        valid_payment_methods = dict(
            Order.PAYMENT_CHOICES
        )

        if payment_method not in valid_payment_methods:

            payment_method = "COD"

        # -------------------------------------------------
        # CHECK REQUIRED FIELDS
        # -------------------------------------------------

        if not all([
            full_name,
            email,
            phone,
            address,
            city,
        ]):

            messages.error(
                request,
                "Please complete all checkout fields.",
            )

            context = get_checkout_context(
                request,
                cart_items,
                cart_count,
                subtotal,
                delivery,
                tax,
                total,
                profile_obj,
            )

            return render(
                request,
                "checkout.html",
                context,
            )

        # -------------------------------------------------
        # EMAIL
        # -------------------------------------------------

        try:

            validate_email(email)

        except ValidationError:

            messages.error(
                request,
                "Please enter a valid email address.",
            )

            context = get_checkout_context(
                request,
                cart_items,
                cart_count,
                subtotal,
                delivery,
                tax,
                total,
                profile_obj,
            )

            return render(
                request,
                "checkout.html",
                context,
            )

        # =================================================
        # CREATE ORDER
        # =================================================

        try:

            with transaction.atomic():

                locked_products = {}

                final_subtotal = Decimal(
                    "0.00"
                )

                # -----------------------------------------
                # LOCK PRODUCTS
                # -----------------------------------------

                for item in cart_items:

                    product = (
                        Product.objects
                        .select_for_update()
                        .get(
                            id=item.product.id
                        )
                    )

                    if product.stock < item.quantity:

                        raise ValueError(
                            f"Only {product.stock} of "
                            f"{product.name} are available."
                        )

                    locked_products[
                        product.id
                    ] = product

                    final_subtotal += (
                        product.price
                        * item.quantity
                    )

                # -----------------------------------------
                # FINAL TOTAL
                # -----------------------------------------

                final_delivery = Decimal(
                    "0.00"
                )

                final_tax = Decimal(
                    "0.00"
                )

                final_total = (
                    final_subtotal
                    + final_delivery
                    + final_tax
                )

                # -----------------------------------------
                # CREATE ORDER
                # -----------------------------------------

                order = Order.objects.create(

                    user=request.user,

                    full_name=full_name,

                    email=email,

                    phone=phone,

                    address=address,

                    city=city,

                    total=final_total,

                    payment_method=payment_method,

                    status="Pending",
                )

                # -----------------------------------------
                # CREATE ORDER ITEMS
                # -----------------------------------------

                for item in cart_items:

                    product = locked_products[
                        item.product.id
                    ]

                    OrderItem.objects.create(

                        order=order,

                        product=product,

                        quantity=item.quantity,

                        price=product.price,
                    )

                    product.stock -= item.quantity

                    product.save(
                        update_fields=["stock"]
                    )

                # -----------------------------------------
                # CLEAR CART
                # -----------------------------------------

                CartItem.objects.filter(
                    user=request.user
                ).delete()

                # -----------------------------------------
                # NOTIFICATION
                # -----------------------------------------

                Notification.objects.create(

                    user=request.user,

                    message=(
                        f"Order #{order.id} "
                        f"has been placed successfully."
                    ),
                )

        except ValueError as e:

            messages.error(
                request,
                str(e),
            )

            return redirect("cart")

        # =================================================
        # ESEWA
        # =================================================

        if payment_method == "ESEWA":

            request.session[
                "esewa_order_id"
            ] = order.id

            request.session.modified = True

            return redirect(
                "esewa_checkout"
            )

        # =================================================
        # COD
        # =================================================

        messages.success(
            request,
            f"Order #{order.id} has been placed successfully.",
        )

        return redirect(
            "order_detail",
            id=order.id,
        )

    # =====================================================
    # GET
    # =====================================================

    context = get_checkout_context(
        request,
        cart_items,
        cart_count,
        subtotal,
        delivery,
        tax,
        total,
        profile_obj,
    )

    return render(
        request,
        "checkout.html",
        context,
    )


# =========================================================
# ORDERS
# =========================================================

@login_required
def orders(request):

    order_list = (
        Order.objects
        .filter(user=request.user)
        .prefetch_related(
            "items__product"
        )
        .order_by("-created_at")
    )

    context = {
        "orders": order_list,
    }

    context.update(
        build_common_context(request)
    )

    return render(
        request,
        "orders.html",
        context,
    )


# =========================================================
# ORDER DETAIL
# =========================================================

@login_required
def order_detail(request, id):

    order = get_object_or_404(
        Order.objects
        .filter(
            id=id,
            user=request.user,
        )
        .prefetch_related(
            "items__product"
        ),
    )

    calculated_total = sum(
        (
            item.price
            * item.quantity
            for item in order.items.all()
        ),
        Decimal("0.00"),
    )

    context = {
        "order": order,
        "order_total": order.total,
        "subtotal": calculated_total,
        "delivery": Decimal("0.00"),
        "tax": Decimal("0.00"),
        "total": order.total,
    }

    context.update(
        build_common_context(request)
    )

    return render(
        request,
        "order_detail.html",
        context,
    )


# =========================================================
# CANCEL ORDER
# =========================================================

@login_required
@require_POST
def cancel_order(request, order_id):

    with transaction.atomic():

        order = get_object_or_404(
            Order.objects
            .select_for_update()
            .prefetch_related(
                "items__product"
            ),
            id=order_id,
            user=request.user,
        )

        if order.status not in [
            "Pending",
            "Processing",
        ]:

            messages.error(
                request,
                "This order cannot be cancelled.",
            )

            return redirect(
                "order_detail",
                id=order.id,
            )

        for item in order.items.all():

            product = (
                Product.objects
                .select_for_update()
                .get(
                    id=item.product.id
                )
            )

            product.stock += item.quantity

            product.save(
                update_fields=["stock"]
            )

        order.status = "Cancelled"

        order.cancelled_by = request.user

        order.cancelled_at = timezone.now()

        order.save(
            update_fields=[
                "status",
                "cancelled_by",
                "cancelled_at",
            ]
        )

        Notification.objects.create(
            user=request.user,
            message=(
                f"Order #{order.id} "
                f"has been cancelled."
            ),
        )

    messages.success(
        request,
        f"Order #{order.id} has been cancelled.",
    )

    return redirect(
        "order_detail",
        id=order.id,
    )


# =========================================================
# NOTIFICATIONS
# =========================================================

@login_required
def notifications(request):

    notification_list = (
        Notification.objects
        .filter(user=request.user)
        .order_by("-created_at")
    )

    context = {
        "notifications": notification_list,
    }

    context.update(
        build_common_context(request)
    )

    return render(
        request,
        "notifications.html",
        context,
    )


# =========================================================
# MARK NOTIFICATION READ
# =========================================================

@login_required
@require_POST
def mark_notification_read(
    request,
    notification_id,
):

    notification = get_object_or_404(
        Notification,
        id=notification_id,
        user=request.user,
    )

    notification.is_read = True

    notification.save(
        update_fields=["is_read"]
    )

    return redirect(
        get_safe_next_url(
            request,
            "notifications",
        )
    )


# =========================================================
# MARK ALL NOTIFICATIONS READ
# =========================================================

@login_required
@require_POST
def mark_all_notifications_read(request):

    Notification.objects.filter(
        user=request.user,
        is_read=False,
    ).update(
        is_read=True
    )

    return redirect(
        get_safe_next_url(
            request,
            "notifications",
        )
    )


# =========================================================
# PAYMENT SUCCESS
# =========================================================

@login_required
def payment_success(request):

    messages.success(
        request,
        "Payment completed successfully.",
    )

    return redirect("orders")


# =========================================================
# ESEWA CHECKOUT
# =========================================================

@login_required
def esewa_checkout(request):

    order_id = request.session.get(
        "esewa_order_id"
    )

    if not order_id:

        messages.error(
            request,
            "No eSewa order found.",
        )

        return redirect("checkout")

    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user,
        status="Pending",
        payment_method="ESEWA",
    )

    esewa = get_esewa_settings()

    payment_url = esewa["payment_url"]

    amount = f"{order.total:.2f}"

    tax_amount = "0"

    total_amount = f"{order.total:.2f}"

    transaction_uuid = (
        f"ORDER-{order.id}-"
        f"{int(time.time())}"
    )

    product_code = esewa["product_code"]

    product_service_charge = "0"

    product_delivery_charge = "0"

    success_url = request.build_absolute_uri(
        "/esewa/success/"
    )

    failure_url = request.build_absolute_uri(
        "/esewa/failure/"
    )

    signed_field_names = (
        "total_amount,"
        "transaction_uuid,"
        "product_code"
    )

    signature = generate_esewa_signature(
        total_amount=total_amount,
        transaction_uuid=transaction_uuid,
        product_code=product_code,
        secret_key=esewa["secret_key"],
    )

    request.session[
        "esewa_transaction_uuid"
    ] = transaction_uuid

    request.session.modified = True

    return render(
        request,
        "esewa_redirect.html",
        {
            "payment_url": payment_url,

            "amount": amount,

            "tax_amount": tax_amount,

            "total_amount": total_amount,

            "transaction_uuid": (
                transaction_uuid
            ),

            "product_code": product_code,

            "product_service_charge": (
                product_service_charge
            ),

            "product_delivery_charge": (
                product_delivery_charge
            ),

            "success_url": success_url,

            "failure_url": failure_url,

            "signed_field_names": (
                signed_field_names
            ),

            "signature": signature,
        },
    )


# =========================================================
# ESEWA SUCCESS
# =========================================================

@login_required
def esewa_success(request):

    encoded_data = request.GET.get(
        "data"
    )

    if not encoded_data:

        messages.error(
            request,
            "Invalid eSewa payment response.",
        )

        return redirect("orders")

    data = decode_esewa_response(
        encoded_data
    )

    if not data:

        messages.error(
            request,
            "Unable to verify eSewa payment response.",
        )

        return redirect("orders")

    esewa = get_esewa_settings()

    # -----------------------------------------------------
    # VERIFY RESPONSE SIGNATURE
    # -----------------------------------------------------

    if not verify_esewa_signature(
        data,
        esewa["secret_key"],
    ):

        messages.error(
            request,
            "eSewa payment verification failed.",
        )

        return redirect("orders")

    # -----------------------------------------------------
    # GET SESSION VALUES
    # -----------------------------------------------------

    order_id = request.session.get(
        "esewa_order_id"
    )

    session_transaction_uuid = (
        request.session.get(
            "esewa_transaction_uuid"
        )
    )

    if not order_id:

        messages.error(
            request,
            "No eSewa order found.",
        )

        return redirect("orders")

    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user,
        payment_method="ESEWA",
    )

    # -----------------------------------------------------
    # VERIFY UUID
    # -----------------------------------------------------

    response_transaction_uuid = str(
        data.get(
            "transaction_uuid",
            "",
        )
    )

    if (
        session_transaction_uuid
        and response_transaction_uuid
        != session_transaction_uuid
    ):

        messages.error(
            request,
            "eSewa transaction does not match this order.",
        )

        return redirect(
            "order_detail",
            id=order.id,
        )

    # -----------------------------------------------------
    # VERIFY PRODUCT CODE
    # -----------------------------------------------------

    if (
        data.get("product_code")
        != esewa["product_code"]
    ):

        messages.error(
            request,
            "Invalid eSewa product code.",
        )

        return redirect(
            "order_detail",
            id=order.id,
        )

    # -----------------------------------------------------
    # VERIFY AMOUNT
    # -----------------------------------------------------

    try:

        response_amount = Decimal(
            str(
                data.get(
                    "total_amount",
                    "0",
                )
            )
        ).quantize(
            Decimal("0.01")
        )

        order_amount = Decimal(
            str(order.total)
        ).quantize(
            Decimal("0.01")
        )

    except (
        TypeError,
        ValueError,
    ):

        messages.error(
            request,
            "Invalid eSewa payment amount.",
        )

        return redirect(
            "order_detail",
            id=order.id,
        )

    if response_amount != order_amount:

        messages.error(
            request,
            "eSewa payment amount does not match the order.",
        )

        return redirect(
            "order_detail",
            id=order.id,
        )

    # -----------------------------------------------------
    # VERIFY STATUS
    # -----------------------------------------------------

    if data.get("status") != "COMPLETE":

        messages.warning(
            request,
            "eSewa payment has not been completed.",
        )

        return redirect(
            "order_detail",
            id=order.id,
        )

    # -----------------------------------------------------
    # SERVER-SIDE STATUS VERIFICATION
    # -----------------------------------------------------

    verification = verify_esewa_transaction(
        transaction_uuid=response_transaction_uuid,
        total_amount=order_amount,
        product_code=esewa["product_code"],
    )

    if not verification:

        messages.error(
            request,
            "Unable to verify your payment with eSewa.",
        )

        return redirect(
            "order_detail",
            id=order.id,
        )

    verification_status = (
        verification.get("status")
    )

    if verification_status != "COMPLETE":

        messages.error(
            request,
            "eSewa could not confirm the payment.",
        )

        return redirect(
            "order_detail",
            id=order.id,
        )

    # -----------------------------------------------------
    # PREVENT DUPLICATE PROCESSING
    # -----------------------------------------------------

    with transaction.atomic():

        locked_order = (
            Order.objects
            .select_for_update()
            .get(
                id=order.id,
                user=request.user,
            )
        )

        if locked_order.status == "Pending":

            locked_order.status = "Processing"

            locked_order.save(
                update_fields=[
                    "status"
                ]
            )

            Notification.objects.create(
                user=request.user,
                message=(
                    f"Payment for Order "
                    f"#{locked_order.id} "
                    f"was completed successfully."
                ),
            )

    # -----------------------------------------------------
    # CLEAR SESSION
    # -----------------------------------------------------

    request.session.pop(
        "esewa_order_id",
        None,
    )

    request.session.pop(
        "esewa_transaction_uuid",
        None,
    )

    request.session.modified = True

    messages.success(
        request,
        "eSewa payment was successful.",
    )

    return redirect("orders")


# =========================================================
# ESEWA FAILURE
# =========================================================

@login_required
def esewa_failure(request):

    order_id = request.session.get(
        "esewa_order_id"
    )

    if not order_id:

        messages.error(
            request,
            "No eSewa order found.",
        )

        return redirect("checkout")

    with transaction.atomic():

        order = get_object_or_404(
            Order.objects
            .select_for_update()
            .prefetch_related(
                "items__product"
            ),
            id=order_id,
            user=request.user,
            payment_method="ESEWA",
        )

        if order.status == "Pending":

            for item in order.items.all():

                product = (
                    Product.objects
                    .select_for_update()
                    .get(
                        id=item.product.id
                    )
                )

                product.stock += item.quantity

                product.save(
                    update_fields=[
                        "stock"
                    ]
                )

            order.status = "Cancelled"

            order.save(
                update_fields=[
                    "status"
                ]
            )

            Notification.objects.create(
                user=request.user,
                message=(
                    f"Order #{order.id} "
                    f"was cancelled because "
                    f"eSewa payment failed."
                ),
            )

    # -----------------------------------------------------
    # CLEAR SESSION
    # -----------------------------------------------------

    request.session.pop(
        "esewa_order_id",
        None,
    )

    request.session.pop(
        "esewa_transaction_uuid",
        None,
    )

    request.session.modified = True

    messages.error(
        request,
        "eSewa payment was cancelled or failed.",
    )

    return redirect("orders")
