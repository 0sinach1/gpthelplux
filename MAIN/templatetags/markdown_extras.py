from django import template
from django.template.defaultfilters import stringfilter
import markdown as md
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter()
@stringfilter
def markdown(value):
    # 'nl2br' extension preserves your line breaks!
    return mark_safe(md.markdown(value, extensions=['nl2br']))