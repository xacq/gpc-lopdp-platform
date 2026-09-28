from django import template

from apps.core.section_help import SECTION_HELP


register = template.Library()


@register.inclusion_tag("includes/section_help_modal.html")
def section_help(key):
    help_content = SECTION_HELP.get(key)
    return {
        "help": help_content,
        "modal_id": f"sectionHelp-{key}",
    }
