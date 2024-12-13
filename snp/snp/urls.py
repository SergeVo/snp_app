from django.contrib import admin
from django.urls import include, path
from django.conf import settings

urlpatterns = [
    path("polls/", include("polls.urls")),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    import debug_toolbar

    urlpatterns += [
        path("__debug__/", include(
            debug_toolbar.urls,
            namespace="debug_toolbar")
            ),
    ]
