"""Add only a bounded KIS window to the qualified direct-payload control."""
from pathlib import Path
import sys

root = Path(sys.argv[1]); files = Path(__file__).resolve().parent
def replace(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, (str(path), text.count(old), old[:80])
    path.write_text(text.replace(old, new))

replace(root/'Makefile', 'CFG += NEO_SINGLE_STAGE\n',
        'CFG += NEO_SINGLE_STAGE\nCFG += NEO_SINGLE_KIS\n')
main = root/'src/main.c'
replace(main, 'const char neo_text_stage_tag[] = "NEO-SINGLE-STAGE-v1";',
        'const char neo_text_stage_tag[] = "NEO-KIS-SINGLE-v1";')
replace(main, '#include "neo-single-stage.inc.c"',
        '#include "neo-single-stage.inc.c"\n#include "neo-single-kis.inc.c"')
replace(main, '    neo_single_begin();\n',
        '    neo_single_begin();\n    neo_single_kis_window();\n')
path = root/'src/neo-single-stage.inc.c'
path.write_text(path.read_text().replace('NEO-SINGLE-STAGE-v1', 'NEO-KIS-SINGLE-v1'))
replace(path, 'USB SETUP SKIPPED; CONTINUING IN 3 SECONDS',
        'KIS WINDOW STARTS IN 3 SECONDS')
(root/'src/neo-single-kis.inc.c').write_bytes((files/'neo-single-kis.inc.c').read_bytes())
