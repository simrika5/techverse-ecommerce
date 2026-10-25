from .models import Wishlist


def wishlist_count(request):
    if request.user.is_authenticated:
        return {
            "wishlist_count": Wishlist.objects.filter(
                user=request.user
            ).count()
        }

    return {
        "wishlist_count": 0
    }



def cart_count(request):

    cart = request.session.get("cart", {})

    total = sum(cart.values())

    return {
        "cart_count": total
    }