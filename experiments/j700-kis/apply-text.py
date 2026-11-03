"""Full-width text console and explicit handoff checkpoints for ESP diagnostics."""
import argparse
from pathlib import Path
import re

def replace(path,old,new):
    text=path.read_text();assert text.count(old)==1,(str(path),text.count(old),old[:70])
    path.write_text(text.replace(old,new))

def span(text,name):
    matches=list(re.finditer(r'(?m)^(?:static )?(?:void|bool) '+re.escape(name)+r'\([^;{}]*\)\s*\{',text))
    assert len(matches)==1,name
    start=matches[0].start();brace=matches[0].end()-1;end=brace+1;depth=1
    while depth:depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return start,brace,end

def apply(root,label):
    assert label in ('NEO-TEXT-TRIAL-v1','NEO-TEXT-RETURN-v1')
    replace(root/'Makefile','CFG += ESP_STAGE2\n','CFG += ESP_STAGE2\nCFG += NEO_TEXT_CONSOLE\n')
    main=root/'src/main.c'
    if '#include "iodev.h"' not in main.read_text():
        replace(main,'#include "utils.h"\n','#include "utils.h"\n#include "iodev.h"\n')
    replace(main,'static bool stage1_window_done;',
            f'const char neo_text_stage_tag[] = "{label}";\n\nstatic bool stage1_window_done;')
    text=main.read_text()
    needle='#if defined(NEO_STAGE2_CONTROL)\n    fb_set_active(true);'
    if needle not in text:needle='#ifdef FB_SILENT_MODE\n    fb_set_active(!cur_boot_args.video.display);'
    start=text.index(needle);end=text.index('#endif',start)+len('#endif')
    original=text[start:end]
    text=text[:start]+'''#ifdef NEO_TEXT_CONSOLE
    fb_clear(int2rgb(0));
    fb_set_active(true);
    printf("\\n%s: FRAMEBUFFER CONSOLE READY\\n", neo_text_stage_tag);
#else
'''+original+'\n#endif'+text[end:]
    main.write_text(text)
    replace(main,'    printf("Preparing to run next stage at %p...\\n", next_stage.entry);',
        '    printf("%s: HANDOFF A: next=%p monitor=%u\\n", neo_text_stage_tag,\n'
        '           next_stage.entry, (unsigned)next_stage.monitor);')
    replace(main,'    usb_cdc_cleanup();\n    exception_shutdown();',
        '    printf("%s: HANDOFF B: NVMe handoff complete\\n", neo_text_stage_tag);\n'
        '    usb_cdc_cleanup();\n    exception_shutdown();')
    replace(main,'    fb_shutdown(next_stage.restore_logo);',
        '    printf("%s: HANDOFF C: console stops here; MMU shutdown and jump follow\\n", neo_text_stage_tag);\n'
        '    iodev_console_flush();\n    mdelay(1000);\n'
        '    fb_shutdown(next_stage.restore_logo);')
    fb=root/'src/fb.c';text=fb.read_text()
    start,brace,end=span(text,'fb_display_logo')
    text=text[:brace+1]+'\n#ifdef NEO_TEXT_CONSOLE\n    return;\n#else\n'+text[brace+1:end-1]+'\n#endif\n}'+text[end:]
    fb.write_text(text)
    layout='''    if (fb.height < fb.width) {
        console.cursor.max_row = (fb.height / console.font.height) - 2 * console.margin.rows;
        console.cursor.max_col =
            ((fb.width - logo->width) / 2) / console.font.width - 2 * console.margin.cols;
    } else { // there aren't much screen real estate for us to waste here
        console.cursor.max_row = (fb.height / console.font.height);
        console.cursor.max_col = (fb.width / console.font.width);
        console.margin.rows = 0;
        console.margin.cols = 0;
    }'''
    replace(fb,layout,'''#ifdef NEO_TEXT_CONSOLE
    console.cursor.max_row = (fb.height / console.font.height) - 2 * console.margin.rows;
    console.cursor.max_col = (fb.width / console.font.width) - 2 * console.margin.cols;
#else
'''+layout+'\n#endif')
    replace(fb,'''    console.active = false;
    fb_clear_console();
    if (restore_logo) {
        fb_restore_logo();
        free(orig_logo.ptr);
        orig_logo.ptr = NULL;
    }''', '''    console.active = false;
#ifndef NEO_TEXT_CONSOLE
    fb_clear_console();
#endif
    if (restore_logo) {
#ifndef NEO_TEXT_CONSOLE
        fb_restore_logo();
#endif
        free(orig_logo.ptr);
        orig_logo.ptr = NULL;
    }''')
    utils=root/'src/utils.c';text=utils.read_text()
    if '#include "../build/build_cfg.h"' not in text:
        text=text.replace('#include <assert.h>','#include "../build/build_cfg.h"\n\n#include <assert.h>',1)
    start,brace,end=span(text,'flush_and_reboot')
    text=text[:start]+'''void flush_and_reboot(void)
{
#ifdef NEO_TEXT_CONSOLE
    printf("NEO-TEXT: REBOOT REQUESTED; PAUSING 5 SECONDS\\n");
    iodev_console_flush();
    mdelay(5000);
#endif
    iodev_console_flush();
    reboot();
}'''+text[end:]
    utils.write_text(text)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--label',required=True)
    args=p.parse_args();apply(args.source,args.label)
