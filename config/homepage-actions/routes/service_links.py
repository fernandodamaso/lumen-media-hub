"""Browser-facing service deep-link bases from Compose host ports."""
import config as settings
from http_support import send_json


def handle_service_links(handler):
    send_json(handler, 200, settings.service_link_bases())
