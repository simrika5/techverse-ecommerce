from django.contrib import admin
from django import forms

from .models import (
    Category,
    Product,
    ProductImage,
    ProductSpecificationGroup,
    ProductSpecification,
    ProductReview,
    CustomerProfile,
    CartItem,
    Order,
    OrderItem,
    Notification,
    Wishlist,
)


# =========================================================
# CATEGORY ADMIN
# =========================================================

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "slug",
        "icon",
    )

    search_fields = (
        "name",
        "slug",
    )

    prepopulated_fields = {
        "slug": ("name",)
    }

    ordering = (
        "name",
    )


# =========================================================
# PRODUCT ADMIN
# =========================================================

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "category",
        "price",
        "stock",
        "created_at",
    )

    list_filter = (
        "category",
        "created_at",
    )

    search_fields = (
        "name",
        "description",
    )

    list_editable = (
        "price",
        "stock",
    )

    ordering = (
        "-created_at",
    )


# =========================================================
# PRODUCT IMAGE ADMIN
# =========================================================

@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):

    list_display = (
        "product",
        "image",
        "display_order",
    )

    list_filter = (
        "product",
    )

    search_fields = (
        "product__name",
    )

    ordering = (
        "product",
        "display_order",
    )


# =========================================================
# PRODUCT SPECIFICATION GROUP ADMIN
# =========================================================

@admin.register(ProductSpecificationGroup)
class ProductSpecificationGroupAdmin(admin.ModelAdmin):

    list_display = (
        "product",
        "name",
        "display_order",
    )

    list_filter = (
        "product",
    )

    search_fields = (
        "product__name",
        "name",
    )

    ordering = (
        "product",
        "display_order",
    )


# =========================================================
# PRODUCT SPECIFICATION ADMIN
# =========================================================

@admin.register(ProductSpecification)
class ProductSpecificationAdmin(admin.ModelAdmin):

    list_display = (
        "group",
        "name",
        "value",
        "display_order",
    )

    list_filter = (
        "group__product",
    )

    search_fields = (
        "name",
        "value",
        "group__name",
        "group__product__name",
    )

    ordering = (
        "group",
        "display_order",
    )


# =========================================================
# PRODUCT REVIEW ADMIN
# =========================================================
#
# Customers create reviews from the website.
#
# Admin can:
# - View reviews
# - Search reviews
# - Filter reviews
# - View review history
#
# Admin cannot:
# - Add reviews
# - Edit reviews
# - Delete reviews
#
# =========================================================

@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):

    list_display = (
        "product",
        "user",
        "rating",
        "title",
        "created_at",
    )

    list_filter = (
        "product",
        "rating",
        "created_at",
    )

    search_fields = (
        "product__name",
        "user__username",
        "title",
        "comment",
    )

    ordering = (
        "-created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# =========================================================
# CUSTOMER PROFILE ADMIN
# =========================================================

@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "phone",
    )

    search_fields = (
        "user__username",
        "phone",
    )


# =========================================================
# CART ITEM ADMIN
# =========================================================

@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "product",
        "quantity",
    )

    search_fields = (
        "user__username",
        "product__name",
    )

    list_filter = (
        "product",
    )


# =========================================================
# ORDER ITEM INLINE
# =========================================================

class OrderItemInline(admin.TabularInline):

    model = OrderItem

    extra = 0

    readonly_fields = (
        "price",
    )


# =========================================================
# ORDER ADMIN FORM
# =========================================================

class OrderAdminForm(forms.ModelForm):

    class Meta:
        model = Order
        fields = "__all__"

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        # -----------------------------------------------------
        # CANCELLED ORDERS ARE READ-ONLY
        # -----------------------------------------------------

        if self.instance and self.instance.pk:
            if self.instance.status == "Cancelled":

                for field_name in self.fields:
                    self.fields[field_name].disabled = True


# =========================================================
# ORDER ADMIN
# =========================================================
#
# STATUS WORKFLOW
#
# Pending
#     ↓
# Processing
#     ↓
# Paid
#     ↓
# Delivered
#
# Cancelled
#     ↓
# Read-only
#
# Pending / Processing / Paid / Delivered:
# - Can be opened
# - Can be edited
# - Status can be changed
#
# Cancelled:
# - Can be opened
# - Can be viewed
# - Cannot be edited
#
# =========================================================

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):

    form = OrderAdminForm

    inlines = [
        OrderItemInline,
    ]

    list_display = (
        "id",
        "user",
        "full_name",
        "total",
        "status",
        "payment_method",
        "payment_reference",
        "created_at",
    )

    list_filter = (
        "status",
        "payment_method",
        "created_at",
    )

    search_fields = (
        "id",
        "full_name",
        "email",
        "phone",
        "user__username",
        "payment_reference",
    )

    ordering = (
        "-created_at",
    )

    readonly_fields = (
        "created_at",
    )

    # ---------------------------------------------------------
    # CANCELLED ORDERS CANNOT BE EDITED
    # ---------------------------------------------------------

    def has_change_permission(self, request, obj=None):

        if obj is not None and obj.status == "Cancelled":
            return True

        return super().has_change_permission(request, obj)

    # ---------------------------------------------------------
    # SAVE ORDER
    # ---------------------------------------------------------

    def save_model(self, request, obj, form, change):

        # -----------------------------------------------------
        # PREVENT CHANGING A CANCELLED ORDER
        # -----------------------------------------------------

        if change:

            old_obj = Order.objects.get(pk=obj.pk)

            if old_obj.status == "Cancelled":
                return

        super().save_model(request, obj, form, change)


# =========================================================
# ORDER ITEM ADMIN
# =========================================================

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):

    list_display = (
        "order",
        "product",
        "quantity",
        "price",
    )

    search_fields = (
        "product__name",
        "order__id",
    )

    list_filter = (
        "product",
    )


# =========================================================
# NOTIFICATION ADMIN
# =========================================================

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "message",
        "is_read",
        "created_at",
    )

    list_filter = (
        "is_read",
        "created_at",
    )

    search_fields = (
        "user__username",
        "message",
    )

    ordering = (
        "-created_at",
    )


# =========================================================
# WISHLIST ADMIN
# =========================================================

@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "product",
        "created_at",
    )

    search_fields = (
        "user__username",
        "product__name",
    )

    ordering = (
        "-created_at",
    )
