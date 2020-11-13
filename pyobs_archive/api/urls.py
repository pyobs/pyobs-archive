from django.urls import path

from . import views

urlpatterns = [
    path('', views.frames_view, name='frames'),
    path('<int:frame_id>/', views.frame_view, name='frame'),
    path('<int:frame_id>/download/', views.download_view, name='download'),
    path('<int:frame_id>/related/', views.related_view, name='related'),
    path('<int:frame_id>/headers/', views.headers_view, name='headers'),
    path('<int:frame_id>/preview/', views.preview_view, name='preview'),
    path('<int:frame_id>/catalog/', views.catalog_view, name='catalog'),
    path('<int:frame_id>/delete/', views.delete_view, name='delete'),
    path('create/', views.create_view, name='create'),
    path('aggregate/', views.aggregate_view, name='options'),
    path('zip/', views.zip_view, name='zip')
]
