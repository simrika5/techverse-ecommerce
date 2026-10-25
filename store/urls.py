from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [

    # =====================================================
    # HOME
    # =====================================================

    path(
        "",
        views.home,
        name="home",
    ),


    # =====================================================
    # PRODUCTS
    # =====================================================

    path(
        "products/",
        views.products,
        name="products",
    ),

    path(
        "product/<int:id>/",
        views.product_detail,
        name="product_detail",
    ),

    path(
        "category/<str:category_name>/",
        views.category_products,
        name="category_products",
    ),


    # =====================================================
    # CART
    # =====================================================

    path(
        "cart/",
        views.cart,
        name="cart",
    ),

    path(
        "add-to-cart/<int:id>/",
        views.add_to_cart,
        name="add_to_cart",
    ),

    path(
        "increase-quantity/<int:id>/",
        views.increase_quantity,
        name="increase_quantity",
    ),

    path(
        "decrease-quantity/<int:id>/",
        views.decrease_quantity,
        name="decrease_quantity",
    ),

    path(
        "update-quantity/<int:id>/",
        views.update_quantity,
        name="update_quantity",
    ),

    path(
        "remove-from-cart/<int:id>/",
        views.remove_from_cart,
        name="remove_from_cart",
    ),


    # =====================================================
    # WISHLIST
    # =====================================================

    path(
        "wishlist/",
        views.wishlist,
        name="wishlist",
    ),

    path(
        "wishlist/add/<int:id>/",
        views.add_wishlist,
        name="add_wishlist",
    ),

    path(
        "wishlist/remove/<int:id>/",
        views.remove_wishlist,
        name="remove_wishlist",
    ),


    # =====================================================
    # REVIEWS
    # =====================================================

    path(
        "product/<int:id>/review/",
        views.add_review,
        name="add_review",
    ),

    path(
        "product/<int:id>/review/delete/",
        views.delete_review,
        name="delete_review",
    ),


    # =====================================================
    # AUTHENTICATION
    # =====================================================

    path(
        "register/",
        views.register,
        name="register",
    ),

    path(
        "login/",
        views.login_view,
        name="login",
    ),

    path(
        "logout/",
        views.logout_view,
        name="logout",
    ),

    path(
        "profile/",
        views.profile,
        name="profile",
    ),


    # =====================================================
    # CHECKOUT
    # =====================================================

    path(
        "checkout/",
        views.checkout,
        name="checkout",
    ),


    # =====================================================
    # ORDERS
    # =====================================================

    path(
        "orders/",
        views.orders,
        name="orders",
    ),

    path(
        "order/<int:id>/",
        views.order_detail,
        name="order_detail",
    ),

    path(
        "order/<int:order_id>/cancel/",
        views.cancel_order,
        name="cancel_order",
    ),


    # =====================================================
    # PAYMENT
    # =====================================================

    path(
        "payment-success/",
        views.payment_success,
        name="payment_success",
    ),

path(
    "esewa/checkout/",
    views.esewa_checkout,
    name="esewa_checkout",
),

path(
    "esewa/success/",
    views.esewa_success,
    name="esewa_success",
),

path(
    "esewa/failure/",
    views.esewa_failure,
    name="esewa_failure",
),


    # =====================================================
    # NOTIFICATIONS
    # =====================================================

    path(
        "notifications/",
        views.notifications,
        name="notifications",
    ),

    path(
        "notifications/<int:notification_id>/read/",
        views.mark_notification_read,
        name="mark_notification_read",
    ),

    path(
        "notifications/read-all/",
        views.mark_all_notifications_read,
        name="mark_all_notifications_read",
    ),
    

    # =====================================================
    # PASSWORD RESET
    # =====================================================

    path(
        "forgot-password/",
        auth_views.PasswordResetView.as_view(
            template_name="forgot_password.html",
            email_template_name="password_reset_email.html",
            subject_template_name="password_reset_subject.txt",
            success_url="/password-reset/done/",
        ),
        name="password_reset",
    ),

    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="password_reset_done.html",
        ),
        name="password_reset_done",
    ),

    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="password_reset_confirm.html",
            success_url="/password-reset/complete/",
        ),
        name="password_reset_confirm",
    ),

    path(
        "password-reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),

]
