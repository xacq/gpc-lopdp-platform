from apps.organization.models import SystemSetting


def branding(request):
    """Provides dynamic branding (logo, favicon, institutional names and custom colors) to templates."""
    try:
        setting = SystemSetting.objects.filter(singleton_key=1).first()
    except Exception:
        setting = None

    if setting is None:
        return {
            "branding": {
                "logo_url": None,
                "favicon_url": None,
                "primary_color": None,
                "secondary_color": None,
                "accent_color": None,
                "legal_name": "VINESA",
                "trade_name": "VINESA",
                "custom_css": "",
            }
        }

    css_parts = []
    if setting.primary_color:
        css_parts.append(f"--vinesa-red: {setting.primary_color};")
    if setting.secondary_color:
        css_parts.append(f"--vinesa-wine: {setting.secondary_color};")
    if setting.accent_color:
        css_parts.append(f"--vinesa-red-dark: {setting.accent_color};")

    custom_css = f":root {{ {' '.join(css_parts)} }}" if css_parts else ""

    return {
        "branding": {
            "logo_url": setting.effective_logo_url,
            "favicon_url": setting.effective_favicon_url,
            "primary_color": setting.primary_color,
            "secondary_color": setting.secondary_color,
            "accent_color": setting.accent_color,
            "legal_name": setting.legal_name,
            "trade_name": setting.trade_name or setting.legal_name,
            "custom_css": custom_css,
        }
    }
