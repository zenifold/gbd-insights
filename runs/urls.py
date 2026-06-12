from django.urls import path

from runs import views

urlpatterns = [
    path("", views.upload_page, name="upload_page"),
    path("template.csv", views.template_csv, name="template_csv"),
    # GBD admin dashboard.
    path("dashboard", views.dashboard, name="dashboard"),
    path("dashboard/runs/<uuid:run_id>", views.run_detail, name="run_detail"),
    path("dashboard/runs/<uuid:run_id>/source", views.download_source, name="download_source"),
    path("runs", views.create_run, name="create_run"),
    path("runs/<uuid:run_id>/finalize", views.finalize_run, name="finalize_run"),
    path("runs/<uuid:run_id>", views.status_page, name="run_status_page"),
    path("runs/<uuid:run_id>/status", views.run_status_partial, name="run_status"),
    path("runs/<uuid:run_id>/download", views.download, name="download"),
    # Local dev storage backend (HMAC-signed; exempt from Basic Auth).
    path("_storage/upload", views.storage_upload, name="storage_upload"),
    path("_storage/download", views.storage_download, name="storage_download"),
]
