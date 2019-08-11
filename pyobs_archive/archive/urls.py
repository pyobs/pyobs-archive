from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('images/', views.ImagesController.as_view(), name='images')
]
