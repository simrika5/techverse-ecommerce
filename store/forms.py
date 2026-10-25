from django import forms
from django.contrib.auth.models import User
from .models import ProductReview


class RegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput())
    confirm_password = forms.CharField(widget=forms.PasswordInput())

    middle_name = forms.CharField(max_length=50, required=False)
    phone = forms.CharField(max_length=15)
    address = forms.CharField(widget=forms.Textarea, required=False)

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "middle_name",
            "phone",
            "address",
            "password",
        ]

    def clean(self):
        cleaned_data = super().clean()

        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password != confirm_password:
            raise forms.ValidationError("Passwords do not match.")

        return cleaned_data


class ProductReviewForm(forms.ModelForm):
    class Meta:
        model = ProductReview
        fields = ["rating", "title", "comment"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "comment": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "rating": forms.Select(attrs={"class": "form-select"}, choices=[(1, "1 star"), (2, "2 stars"), (3, "3 stars"), (4, "4 stars"), (5, "5 stars")]),
        }

    def clean_rating(self):
        rating = self.cleaned_data.get("rating")
        if rating is None or rating < 1 or rating > 5:
            raise forms.ValidationError("Please choose a valid rating between 1 and 5.")
        return rating

    def clean_comment(self):
        comment = self.cleaned_data.get("comment")
        if comment and len(comment.strip()) < 2:
            raise forms.ValidationError("Please write a more useful review.")
        return comment