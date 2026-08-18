from django import template
from django.forms import CheckboxInput, RadioSelect, Select


register = template.Library()


@register.filter
def bootstrap_field(bound_field):
    """Render a bound field with Bootstrap classes without mutating the form."""
    widget = bound_field.field.widget
    attrs = dict(widget.attrs)

    if isinstance(widget, CheckboxInput):
        css_class = "form-check-input"
    elif isinstance(widget, (Select, RadioSelect)):
        css_class = "form-select"
    else:
        css_class = "form-control"

    current_classes = attrs.get("class", "").split()
    if css_class not in current_classes:
        current_classes.append(css_class)
    if bound_field.errors and "is-invalid" not in current_classes:
        current_classes.append("is-invalid")
    attrs["class"] = " ".join(current_classes)

    return bound_field.as_widget(attrs=attrs)
