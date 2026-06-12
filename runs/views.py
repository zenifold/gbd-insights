from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.paginator import Paginator
from django.http import (
    FileResponse,
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from runs.models import AnalysisRun, Client, RunStatus, Tag
from runs.scoping import client_for, get_run_for, is_gbd_staff, visible_runs
from runs.storage import get_storage
from runs.storage.local import LocalStorage
from runs.storage.signing import verify

ALLOWED_EXT = settings.ALLOWED_UPLOAD_EXTENSIONS


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------
@require_GET
def upload_page(request):
    staff = is_gbd_staff(request.user)
    return render(
        request,
        "upload.html",
        {
            "max_mb": settings.MAX_UPLOAD_BYTES // (1024 * 1024),
            "is_staff": staff,
            "client": client_for(request.user),
            "tags": Tag.objects.all() if staff else None,
        },
    )


TEMPLATE_CSV = (
    "product,vendor,spend,quantity,unit,date\n"
    "Ground Beef 80/20,US Foods,1240.50,200,lb,2026-01-15\n"
    "Chicken Breast Boneless,Sysco,980.00,300,lb,2026-01-15\n"
    "Black Beans Canned,US Foods,210.75,150,can,2026-01-15\n"
    "Tofu Firm,Local Farm Co,145.20,80,block,2026-01-15\n"
)


# --------------------------------------------------------------------------
# Runs dashboard — scoped to the user: GBD staff see every client's runs;
# a client self-serve user sees only their own organization's runs.
# --------------------------------------------------------------------------
@require_GET
def dashboard(request):
    staff = is_gbd_staff(request.user)
    runs = visible_runs(request.user).prefetch_related("tags")

    cur_status = request.GET.get("status", "")
    if cur_status in RunStatus.values:
        runs = runs.filter(status=cur_status)

    cur_tag = request.GET.get("tag", "")
    if cur_tag:
        runs = runs.filter(tags__slug=cur_tag)

    query = (request.GET.get("q") or "").strip()
    if query:
        runs = runs.filter(source_filename__icontains=query)

    page = Paginator(runs, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "dashboard.html",
        {
            "page": page,
            "statuses": RunStatus.choices,
            "is_staff": staff,
            "tags": Tag.objects.all(),
            "cur_status": cur_status,
            "cur_tag": cur_tag,
            "query": query,
        },
    )


@require_GET
def run_detail(request, run_id):
    # Admin metadata view — GBD staff only.
    if not is_gbd_staff(request.user):
        raise Http404()
    run = get_run_for(request.user, run_id)
    return render(
        request,
        "run_detail.html",
        {"run": run, "summary_pretty": json.dumps(run.summary, indent=2, sort_keys=True)},
    )


@require_GET
def download_source(request, run_id):
    """Mint a signed link to the original uploaded file (GBD staff, troubleshooting)."""
    if not is_gbd_staff(request.user):
        raise Http404()
    run = get_run_for(request.user, run_id)
    if not run.source_path:
        raise Http404("No source file recorded")
    filename = run.source_filename or f"source-{run.id}"
    return redirect(get_storage().create_signed_download(run.source_path, filename=filename))


@require_GET
def template_csv(request):
    response = HttpResponse(TEMPLATE_CSV, content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="gbd-procurement-template.csv"'
    return response


@require_GET
def status_page(request, run_id):
    run = get_run_for(request.user, run_id)
    return render(request, "status.html", {"run": run})


@require_GET
def run_status_partial(request, run_id):
    run = get_run_for(request.user, run_id)
    return render(request, "partials/_status.html", {"run": run})


@require_GET
def download(request, run_id):
    run = get_run_for(request.user, run_id)
    if run.status != RunStatus.DONE or not run.artifact_path:
        raise Http404("Report not available")
    suffix = Path(run.artifact_path).suffix or ".bin"
    filename = f"gbd-report-{run.id}{suffix}"
    url = get_storage().create_signed_download(run.artifact_path, filename=filename)
    return redirect(url)


# --------------------------------------------------------------------------
# Upload flow (two-step direct-to-storage)
# --------------------------------------------------------------------------
@require_POST
def create_run(request):
    filename = (request.POST.get("filename") or "").strip()
    content_type = request.POST.get("content_type", "")

    # GBD staff name the client freely (created on the fly) and optionally tag it;
    # a client user can only upload for their own organization.
    tag_slugs: list[str] = []
    if is_gbd_staff(request.user):
        client_name = (request.POST.get("client_name") or "").strip()
        client_id = request.POST.get("client_id")
        if client_name:
            client, _ = Client.objects.get_or_create(
                slug=slugify(client_name)[:255] or "client", defaults={"name": client_name}
            )
        elif client_id:
            client = get_object_or_404(Client, id=client_id)
        else:
            client, _ = Client.objects.get_or_create(slug="ad-hoc", defaults={"name": "Ad hoc"})
        tag_slugs = request.POST.getlist("tags")
    else:
        client = client_for(request.user)
        if client is None:
            return HttpResponseBadRequest("Your account isn't linked to a client. Contact GBD.")

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        allowed = " or ".join(ALLOWED_EXT)
        return HttpResponseBadRequest(f"Please upload a {allowed} file.")

    run = AnalysisRun.objects.create(
        client=client,
        created_by=request.user.get_username(),
        source_filename=filename,
        source_path="",  # set below once we know the run id
        status=RunStatus.PENDING_UPLOAD,
    )
    run.source_path = f"uploads/{client.slug}/{run.id}/source{ext}"
    run.save(update_fields=["source_path", "updated_at"])
    if tag_slugs:
        run.tags.set(Tag.objects.filter(slug__in=tag_slugs))

    signed = get_storage().create_signed_upload(run.source_path, content_type=content_type)
    return JsonResponse(
        {
            "run_id": str(run.id),
            "upload": {"url": signed.url, "method": signed.method, "headers": signed.headers},
            "finalize_url": reverse("finalize_run", args=[run.id]),
            "status_url": reverse("run_status_page", args=[run.id]),
        }
    )


@require_POST
def finalize_run(request, run_id):
    run = get_run_for(request.user, run_id)
    if run.status != RunStatus.PENDING_UPLOAD:
        # Idempotent: already finalized.
        return JsonResponse({"status": run.status, "status_url": reverse("run_status_page", args=[run.id])})

    stat = get_storage().stat(run.source_path)
    if not stat.exists:
        return JsonResponse(
            {"error": "We didn't receive your file. Please try the upload again."}, status=400
        )

    run.source_bytes = stat.size
    run.status = RunStatus.QUEUED
    run.save(update_fields=["source_bytes", "status", "updated_at"])

    # Free single-service hosting: process the run now instead of via a worker.
    if settings.PROCESS_INLINE:
        import os

        from runs.processing import drain_queue

        try:
            drain_queue(f"web:{os.getpid()}")
        except Exception:  # never fail finalize on a processing error
            pass
        run.refresh_from_db()

    return JsonResponse(
        {"status": run.status, "status_url": reverse("run_status_page", args=[run.id])}
    )


# --------------------------------------------------------------------------
# Local storage backend endpoints (dev only; secured by HMAC signed URL token).
# Exempt from Basic Auth (see BASIC_AUTH_EXEMPT_PREFIXES) and from CSRF (the
# token is the authenticator).
# --------------------------------------------------------------------------
def _verify_signed(request, action: str) -> str:
    path = request.GET.get("path", "")
    try:
        exp = int(request.GET.get("exp", "0"))
    except ValueError:
        exp = 0
    sig = request.GET.get("sig", "")
    if not path or not verify(path, action, exp, sig):
        raise Http404("Invalid or expired link")
    return path


@csrf_exempt
def storage_upload(request):
    if request.method != "PUT":
        return HttpResponse(status=405)
    if not isinstance(get_storage(), LocalStorage):
        raise Http404()
    path = _verify_signed(request, "upload")
    try:
        size = get_storage().write_stream(path, request, max_bytes=settings.MAX_UPLOAD_BYTES)
    except ValueError:
        limit_mb = settings.MAX_UPLOAD_BYTES // (1024 * 1024)
        return HttpResponse(f"File exceeds the {limit_mb} MB limit.", status=413)
    return JsonResponse({"size": size}, status=200)


@require_GET
def storage_download(request):
    if not isinstance(get_storage(), LocalStorage):
        raise Http404()
    path = _verify_signed(request, "download")
    filename = request.GET.get("filename") or Path(path).name
    fh = get_storage().open_for_read(path)
    response = FileResponse(fh, as_attachment=True, filename=filename)
    return response
