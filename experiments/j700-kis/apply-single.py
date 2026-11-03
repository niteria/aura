"""Apply the direct-OS control after the existing text-only return-stage patch."""
from pathlib import Path
import sys

root = Path(sys.argv[1])
files = Path(__file__).resolve().parent

def replace(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, (str(path), text.count(old), old[:80])
    path.write_text(text.replace(old, new))

replace(root / 'Makefile', 'CFG += NEO_TEXT_CONSOLE\n',
        'CFG += NEO_TEXT_CONSOLE\nCFG += NEO_SINGLE_STAGE\n')
main = root / 'src/main.c'
replace(main, '#include "monitor.h"\n', '#include "monitor.h"\n#include "kboot.h"\n')
replace(main, 'const char neo_text_stage_tag[] = "NEO-TEXT-RETURN-v1";',
        'const char neo_text_stage_tag[] = "NEO-SINGLE-STAGE-v1";\n'
        '#include "neo-single-stage.inc.c"')
replace(main, 'void run_actions(void)\n{\n',
        'void run_actions(void)\n{\n    neo_single_begin();\n')
replace(main, '    bool payload_valid = payload_run() == 0;\n',
        '    bool payload_valid = payload_run() == 0;\n'
        '    if (!payload_valid)\n'
        '        panic("NEO-SINGLE-STAGE-v1: payload failed; USB fallback disabled\\n");\n')
replace(main, '    printf("%s: HANDOFF A: next=%p monitor=%u\\n", neo_text_stage_tag,',
        '    neo_single_finish();\n'
        '    printf("%s: HANDOFF A: next=%p monitor=%u\\n", neo_text_stage_tag,')
(root / 'src/neo-single-stage.inc.c').write_bytes((files / 'neo-single-stage.inc.c').read_bytes())
