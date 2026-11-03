"""Check the real text-layout/logo/shutdown code and panic/reset ordering."""
import json
from pathlib import Path
import re
import subprocess
import sys

root,out=map(Path,sys.argv[1:])
fb=(root/'src/fb.c').read_text();utils=(root/'src/utils.c').read_text();main=(root/'src/main.c').read_text()
def function(text,name):
    m=list(re.finditer(r'(?m)^(?:static )?(?:void|bool) '+re.escape(name)+r'\([^;{}]*\)\s*\{',text))
    assert len(m)==1,name
    start=m[0].start();i=m[0].end();depth=1
    while depth:depth+=(text[i]=='{')-(text[i]=='}');i+=1
    return text[start:i]
start=fb.index('#ifdef NEO_TEXT_CONSOLE\n    console.cursor.max_row')
layout=fb[start:fb.index('#endif',start)+len('#endif')]
assert 'HANDOFF A' in main and 'HANDOFF B' in main and 'HANDOFF C' in main
assert main.index('HANDOFF C')<main.index('fb_shutdown(next_stage.restore_logo)')<main.index('mmu_shutdown();')
prefix=r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <setjmp.h>
#define NEO_TEXT_CONSOLE 1
static struct { void *ptr;unsigned width,height; } fb;
static struct { bool initialized,active;struct {unsigned width,height;} font;
  struct {unsigned rows,cols;} margin;struct {unsigned max_row,max_col;} cursor;} console;
static struct {void *ptr;} orig_logo;
static unsigned clears,restores,frees,holds,flushes,resets;
static char a,b;
static jmp_buf done;
static void fb_clear_console(void) {clears++;}
static void fb_restore_logo(void) {restores++;}
static void release(void *p) {assert(p==&a||p==&b);frees++;}
#define free release
static void iodev_console_flush(void) {flushes++;}
static void mdelay(unsigned n) {assert(n==5000&&flushes==1);holds++;}
static _Noreturn void reboot(void) {assert(holds==1&&flushes==2);resets++;longjmp(done,1);}
'''
shutdown=function(fb,'fb_shutdown')
body='static void layout(void) {\n'+layout+'\n}\n'
body+=function(fb,'fb_display_logo')+'\n'+shutdown.replace('fb_shutdown','text_shutdown',1)
body+='\n#undef NEO_TEXT_CONSOLE\n'+shutdown.replace('fb_shutdown','normal_shutdown',1)
body+='\n#define NEO_TEXT_CONSOLE 1\n'+function(utils,'flush_and_reboot')
tests=r'''
static void reset(void) {clears=restores=frees=0;console.initialized=console.active=true;fb.ptr=&a;orig_logo.ptr=&b;}
int main(void) {
 fb.width=2408;fb.height=1506;console.font.width=16;console.font.height=32;
 console.margin.cols=4;console.margin.rows=2;layout();
 assert(console.cursor.max_col==142&&console.cursor.max_row==43);
 fb_display_logo();
 reset();text_shutdown(true);assert(!console.active&&!console.initialized&&clears==0&&restores==0&&frees==2);
 reset();text_shutdown(false);assert(clears==0&&restores==0&&frees==1&&orig_logo.ptr==&b);
 reset();normal_shutdown(true);assert(clears==1&&restores==1&&frees==2);
 if(!setjmp(done)){flush_and_reboot();assert(!"reset returned");}
 assert(resets==1);
 puts("PASS: full-width layout, logo suppressed, handoff pixels preserved, lifecycle unchanged, panic pause");
}
'''
c=out/'actual-text.c';c.write_text(prefix+body+tests);exe=out/'actual-text'
subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(c),'-o',str(exe)],check=True)
r=subprocess.run([str(exe)],text=True,capture_output=True,check=True)
(out/'stdout.txt').write_text(r.stdout)
(out/'passed.json').write_text(json.dumps(dict(passed=True,actual_c=True,columns=142,rows=43,
 no_logo=True,preserve_handoff_pixels=True,panic_pause=True),indent=2)+'\n')
print(r.stdout)
