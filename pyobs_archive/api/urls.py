from django.urls import path

from . import views

urlpatterns = [
    path('frames/', views.frames_view, name='frames'),
    path('frames/<int:frame_id>/', views.frame_view, name='frame'),
    path('frames/<int:frame_id>/download/', views.download_view, name='download'),
    path('frames/<int:frame_id>/related/', views.related_view, name='related'),
    path('frames/<int:frame_id>/headers/', views.headers_view, name='headers'),
    path('frames/<int:frame_id>/preview/', views.preview_view, name='preview'),
    path('frames/create/', views.create_view, name='create'),
    path('frames/aggregate/', views.aggregate_view, name='options'),
    path('frames/zip/', views.zip_view, name='zip')
]
