/* The real control must preserve trial ownership and evidence on every outcome. */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <setjmp.h>
#define min(a,b) ((a)<(b)?(a):(b))
char con_buf[8192];
size_t con_wp;
static bool admitted = true, sync_result;
static unsigned arms, fail_arm, enables, waits, sessions, records;
static int enable_result, session_result, record_result;
static char saved_outcome[96], saved_log[4097];
static jmp_buf rejected;
static bool neo_single_admitted(void) { return admitted; }
static int wdt_arm_seconds(unsigned seconds)
{
    assert(seconds == 178); arms++; return arms == fail_arm ? -1 : 0;
}
static int tps6598x_enable_debugusb(void) { enables++; return enable_result; }
static bool uartproxy_wait_dockchannel(unsigned ms)
{
    assert(ms == 30000 && enables == 1 && arms == 1); waits++; return sync_result;
}
static int uartproxy_run_presynced(void) { sessions++; return session_result; }
static int kboot_set_chosen(const char *name, const char *value)
{
    records++;
    if (!strcmp(name,"aurora,kis-window")) {
        assert(strlen(value) < sizeof(saved_outcome)); strcpy(saved_outcome,value);
    } else {
        assert(!strcmp(name,"aurora,kis-log"));
        assert(strlen(value) < sizeof(saved_log)); strcpy(saved_log,value);
    }
    return record_result;
}
static _Noreturn void panic(const char *message)
{
    (void)message; longjmp(rejected,1);
}
#include "neo-single-kis.inc.c"
static void reset(void)
{
    admitted=true; sync_result=false; arms=fail_arm=enables=waits=sessions=records=0;
    enable_result=record_result=0; session_result=1;
    saved_outcome[0]=saved_log[0]=0;
    memset(con_buf,0,sizeof(con_buf)); con_wp=0;
}
static void reject(void)
{
    if (!setjmp(rejected)) { neo_single_kis_window(); assert(!"unexpected successful return"); }
}
int main(void)
{
    reset(); admitted=false; reject(); assert(!arms&&!enables&&!waits&&!records);
    reset(); fail_arm=1; neo_single_kis_window();
    assert(arms==1&&!enables&&!waits&&records==2&&!strcmp(saved_outcome,"watchdog-unavailable"));
    reset(); enable_result=-1; neo_single_kis_window();
    assert(arms==2&&enables==1&&!waits&&!sessions&&records==2);
    assert(!strcmp(saved_outcome,"enable=-1 sync=0 session=0"));
    reset(); neo_single_kis_window();
    assert(arms==2&&waits==1&&!sessions&&records==2&&!strcmp(saved_outcome,"enable=0 sync=0 session=0"));
    reset(); sync_result=true; neo_single_kis_window();
    assert(arms==2&&waits==1&&sessions==1&&records==2&&!strcmp(saved_outcome,"enable=0 sync=1 session=1"));
    reset(); sync_result=true; session_result=-1; reject(); assert(arms==2&&!records);
    reset(); sync_result=true; session_result=2; reject(); assert(arms==2&&!records);
    reset(); fail_arm=2; reject(); assert(!records);
    reset(); record_result=-1; reject(); assert(records==1);
    reset(); memcpy(con_buf,"known error\n",12);con_wp=12;neo_kis_record("test");
    assert(!strcmp(saved_log,"known error\n"));
    reset();
    for(size_t i=0;i<12345;i++) con_buf[i%sizeof(con_buf)]='A'+i%26;
    con_wp=12345;neo_kis_record("wrapped");assert(strlen(saved_log)==4096);
    for(size_t i=0;i<4096;i++) assert(saved_log[i]==(char)('A'+(12345-4096+i)%26));
    puts("PASS: actual KIS admission, timeout/exit/error handling, watchdog lifecycle and bounded ring export");
}
