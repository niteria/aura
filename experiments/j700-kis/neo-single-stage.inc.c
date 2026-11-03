/* SPDX-License-Identifier: GPL-2.0-only */
/* ESP-only J700 control: use the original OS payload without another Aura hop. */
static bool neo_single_admitted(void)
{
    return chip_id == T8140 && board_id == 0x64 && aura_trial_enabled() &&
           cur_boot_args.revision == 3 &&
           !memcmp(cur_boot_args.rv3.cmdline, "aura-trial", sizeof("aura-trial"));
}

static void neo_single_begin(void)
{
    if (!neo_single_admitted())
        panic("NEO-SINGLE-STAGE-v1: not an admitted J700 one-shot trial\n");
    if (kboot_set_chosen("aurora,single-stage", neo_text_stage_tag) < 0)
        panic("NEO-SINGLE-STAGE-v1: could not register the boot witness\n");
    printf("%s: DIRECT ORIGINAL OS PAYLOAD; NO EXTRA AURA STAGE\n", neo_text_stage_tag);
    printf("NEO-SINGLE-STAGE-v1: USB SETUP SKIPPED; CONTINUING IN 3 SECONDS\n");
    mdelay(3000);
}

static void neo_single_finish(void)
{
    if (!neo_single_admitted() || !next_stage.entry || !next_stage.monitor)
        panic("NEO-SINGLE-STAGE-v1: refusing an unexpected final handoff\n");
    /* Linux has no Apple watchdog driver. Match the normal OS handoff, which
     * disables this timer, rather than passing an unserviced trial timer on. */
    cur_boot_args.rv3.cmdline[0] = 0;
    boot_options_set_trial(false);
    wdt_disable();
    printf("NEO-SINGLE-STAGE-v1: trial timer cleared; entering original OS payload\n");
}
