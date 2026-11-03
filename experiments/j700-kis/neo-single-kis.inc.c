/* SPDX-License-Identifier: GPL-2.0-only */
/* Keep an outcome and the pre-payload console even when no USB host attaches. */
extern char con_buf[];
extern size_t con_wp;

static void neo_kis_record(const char *outcome)
{
    static char snapshot[4097];
    size_t len = min(con_wp, sizeof(snapshot) - 1);
    for (size_t i = 0; i < len; i++)
        snapshot[i] = con_buf[(con_wp - len + i) % 8192];
    snapshot[len] = 0;
    if (kboot_set_chosen("aurora,kis-window", outcome) < 0 ||
        kboot_set_chosen("aurora,kis-log", snapshot) < 0)
        panic("NEO-KIS-SINGLE-v1: could not preserve KIS evidence\n");
}

static void neo_single_kis_window(void)
{
    if (!neo_single_admitted())
        panic("NEO-KIS-SINGLE-v1: KIS window admission failed\n");
    if (wdt_arm_seconds(178)) {
        printf("NEO-KIS-SINGLE-v1: watchdog unavailable; skipping KIS\n");
        neo_kis_record("watchdog-unavailable");
        return;
    }
    printf("NEO-KIS-SINGLE-v1: enabling DebugUSB on the existing hpm0 route\n");
    int enabled = tps6598x_enable_debugusb();
    bool synced = false;
    int session = 0;
    if (enabled >= 0) {
        printf("NEO-KIS-SINGLE-v1: waiting up to 30 seconds on DockChannel UART\n");
        synced = uartproxy_wait_dockchannel(30000);
        if (synced)
            session = uartproxy_run_presynced();
    }
    printf("NEO-KIS-SINGLE-v1: enable=%d sync=%u session=%d\n", enabled, synced, session);
    if (wdt_arm_seconds(178))
        panic("NEO-KIS-SINGLE-v1: watchdog rearm failed\n");
    if (synced && session != 1)
        panic("NEO-KIS-SINGLE-v1: proxy did not exit cleanly\n");
    char outcome[96];
    snprintf(outcome, sizeof(outcome), "enable=%d sync=%u session=%d", enabled, synced, session);
    neo_kis_record(outcome);
    printf("NEO-KIS-SINGLE-v1: continuing directly into the original OS payload\n");
}
