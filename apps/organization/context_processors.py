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
                "background_color": None,
                "legal_name": "Organización",
                "trade_name": "Organización",
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

    css_variables = {
        "background_color": "--theme-background",
        "active_color": "--theme-active",
        "separator_color": "--theme-separator",
        "border_color": "--theme-border",
        "secondary_text_color": "--theme-text-secondary",
        "success_color": "--theme-success",
        "info_color": "--theme-info",
        "warning_color": "--theme-warning",
        "error_color": "--theme-error",
    }
    for field, variable in css_variables.items():
        value = getattr(setting, field)
        if value:
            css_parts.append(f"{variable}: {value};")

    custom_css = f":root {{ {' '.join(css_parts)} }}" if css_parts else ""

    logo_url = setting.effective_logo_url
    if setting.logo_image and logo_url and setting.updated_at:
        logo_url = f"{logo_url}?v={int(setting.updated_at.timestamp())}"

    return {
        "branding": {
            "logo_url": logo_url,
            "favicon_url": setting.effective_favicon_url,
            "primary_color": setting.primary_color,
            "secondary_color": setting.secondary_color,
            "accent_color": setting.accent_color,
            **{field: getattr(setting, field) for field in css_variables},
            "legal_name": setting.legal_name,
            "trade_name": setting.trade_name or setting.legal_name,
            "custom_css": custom_css,
        }
    }
