/* Exercise the actual control, including rejected identities and timer ownership. */
#include <assert.h>
#include <stdbool.h>
#include <setjmp.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#define T8140 0x8140
static unsigned chip_id, board_id;
static struct { unsigned revision; struct { char cmdline[512]; } rv3; } cur_boot_args;
static struct { void *entry; bool monitor; } next_stage;
static const char neo_text_stage_tag[] = "NEO-SINGLE-STAGE-v1";
static bool trial;
static int chosen_result;
static unsigned chosen_calls, waits, disables, panics;
static jmp_buf rejected;
static bool aura_trial_enabled(void) { return trial; }
static void boot_options_set_trial(bool value) { trial = value; }
static void wdt_disable(void)
{
    assert(!trial && cur_boot_args.rv3.cmdline[0] == 0);
    disables++;
}
static int kboot_set_chosen(const char *name, const char *value)
{
    assert(!strcmp(name, "aurora,single-stage"));
    assert(!strcmp(value, neo_text_stage_tag));
    assert(trial && disables == 0);
    chosen_calls++;
    return chosen_result;
}
static void mdelay(unsigned ms)
{
    assert(ms == 3000 && chosen_calls == 1 && chosen_result >= 0);
    assert(trial && disables == 0);
    waits++;
}
static _Noreturn void panic(const char *format, ...)
{
    (void)format;
    panics++;
    longjmp(rejected, 1);
}

#include "neo-single-stage.inc.c"

static void reset(void)
{
    chip_id = T8140; board_id = 0x64; trial = true;
    memset(&cur_boot_args, 0, sizeof(cur_boot_args));
    cur_boot_args.revision = 3;
    strcpy(cur_boot_args.rv3.cmdline, "aura-trial");
    next_stage.entry = &next_stage;
    next_stage.monitor = true;
    chosen_result = 0;
    chosen_calls = waits = disables = panics = 0;
}
static void expect_rejection(void (*action)(void))
{
    unsigned old_disables = disables;
    bool old_trial = trial;
    char old_line[sizeof(cur_boot_args.rv3.cmdline)];
    memcpy(old_line, cur_boot_args.rv3.cmdline, sizeof(old_line));
    if (!setjmp(rejected)) {
        action();
        assert(!"invalid control returned");
    }
    assert(panics == 1 && disables == old_disables && trial == old_trial);
    assert(!memcmp(old_line, cur_boot_args.rv3.cmdline, sizeof(old_line)));
}
int main(void)
{
    reset(); chip_id++; expect_rejection(neo_single_begin);
    reset(); board_id++; expect_rejection(neo_single_begin);
    reset(); trial = false; expect_rejection(neo_single_begin);
    reset(); cur_boot_args.revision = 2; expect_rejection(neo_single_begin);
    reset(); cur_boot_args.rv3.cmdline[0] = 0; expect_rejection(neo_single_begin);
    reset(); strcpy(cur_boot_args.rv3.cmdline, "aura-trial extra"); expect_rejection(neo_single_begin);
    reset(); strcpy(cur_boot_args.rv3.cmdline, "aura-trials"); expect_rejection(neo_single_begin);
    reset(); memset(cur_boot_args.rv3.cmdline, 'x', sizeof(cur_boot_args.rv3.cmdline));
    expect_rejection(neo_single_begin);
    reset(); chosen_result = -1; expect_rejection(neo_single_begin);
    assert(chosen_calls == 1 && waits == 0);
    reset(); next_stage.entry = NULL; expect_rejection(neo_single_finish);
    reset(); next_stage.monitor = false; expect_rejection(neo_single_finish);
    reset(); cur_boot_args.revision = 2; expect_rejection(neo_single_finish);
    reset(); neo_single_begin();
    assert(chosen_calls == 1 && waits == 1 && disables == 0 && trial);
    neo_single_finish();
    assert(disables == 1 && !trial && !cur_boot_args.rv3.cmdline[0] && !panics);
    expect_rejection(neo_single_finish);
    puts("PASS: actual C admission, failure paths, boot witness, single monitor handoff, timer lifecycle");
    return 0;
}
