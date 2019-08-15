from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('frames/', views.frames, name='frames'),
    path('create/', views.create_view, name='create'),
    path('frames/aggregate/', views.options, name='options')
]
