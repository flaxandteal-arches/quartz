import re
from django_hosts import patterns, host

host_patterns = patterns(
    "",
    host(re.sub(r"_", r"-", r"quartz"), "quartz.urls", name="quartz"),
)
