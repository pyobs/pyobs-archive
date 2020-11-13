from django.urls import path

from . import views

urlpatterns = [
    path('<int:frame_id>/', views.js9, name='js9'),
]
