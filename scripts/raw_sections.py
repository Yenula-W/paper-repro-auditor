"""Print availability-like sections, hyperlinks and request phrases straight from a cached
Europe PMC XML / PDF, independently of the auditor's own extraction (hand-check aid)."""
import re
import sys

x = open(sys.argv[1], encoding="utf-8", errors="replace").read()
x = re.sub(r"<ref-list.*?</ref-list>", "", x, flags=re.S)
for m in re.finditer(r"(?i)<(title|meta-name|bold)>([^<]*(?:availab|accessib|deposit|data records|software)[^<]*)</\1>", x):
    seg = x[m.end():m.end() + 2500].split("<title>")[0]
    seg = re.sub(r'<ext-link[^>]*href="([^"]*)"[^>]*>', r" [\1] ", seg)
    print("SECTION:", m.group(2), "::", " ".join(re.sub(r"<[^>]+>", " ", seg).split())[:900])
print("HREFS:", [h for h in sorted(set(re.findall(r'xlink:href="(https?://[^"]+)"', x))) if "creativecommons" not in h][:40])
print("REQUEST:", [" ".join(re.sub("<[^>]+>", "", x[max(0, m.start() - 120):m.end() + 60]).split())
                   for m in re.finditer(r"(?i)(up)?on\s+(reasonable\s+)?request", x)][:4])
print("SOFTWARE:", sorted(set(m.group(0) for m in re.finditer(r"\b(R Core|SPSS|Stata|SAS|MATLAB|Python|GraphPad|Prism|ImageJ|Fiji|lme4|custom (?:code|script)s?)\b", x)))[:12])
