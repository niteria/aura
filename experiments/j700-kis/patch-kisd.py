"""Scope the public bridge to one device, validated A18 binding and an owned PTY link."""
from pathlib import Path
import sys

path = Path(sys.argv[1])/'src/main.rs'
text = path.read_text()
def replace(old, new):
    global text
    assert text.count(old) == 1, (text.count(old), old[:100])
    text = text.replace(old, new)

replace('    DeviceNotFound,\n',
        '    DeviceNotFound,\n    #[error("Multiple DebugUSB devices present")]\n    AmbiguousDevice,\n')
replace('''        let device = list_devices()
            .await?
            .find(|dev| dev.vendor_id() == 0x05ac && dev.product_id() == 0x1881)
            .ok_or(DebugUsbError::DeviceNotFound)?;''', '''        let mut devices = list_devices().await?
            .filter(|dev| dev.vendor_id() == 0x05ac && dev.product_id() == 0x1881);
        let device = devices.next().ok_or(DebugUsbError::DeviceNotFound)?;
        if devices.next().is_some() {
            return Err(DebugUsbError::AmbiguousDevice);
        }''')
start = text.index('        let mut descriptor = self.req(cfg_ep, buf.freeze()).await?;')
end = text.index('\n    async fn enable_portals', start)
text = text[:start]+'''        let descriptor = self.req(cfg_ep, buf.freeze()).await?;
        self.base = neo_descriptor_base(self.device_version, &descriptor)?;
        let free = self.uart_tx_free(0).await?;
        log::info!("NEO_KIS_BINDING_OK version={:04x} base=0x{:x} channel=0 free={}",
                   self.device_version, self.base, free);
        Ok(())
    }
'''+text[end:]
replace('''        let hdr_bytes = resp.split_to(std::mem::size_of::<KisHeader>());''',
        '''        if resp.len() < std::mem::size_of::<KisHeader>() + 12 {
            return Err(DebugUsbError::Read);
        }
        let hdr_bytes = resp.split_to(std::mem::size_of::<KisHeader>());''')
replace('''    channel: u8,
}''', '''    channel: u8,
    #[arg(long, default_value = "/dev/m1n1")]
    link: std::path::PathBuf,
    #[arg(long)]
    once: bool,
}''')
replace('tokio::fs::remove_file(&"/dev/m1n1")', 'tokio::fs::remove_file(&args.link)')
replace('tokio::fs::symlink(pty.name(), &"/dev/m1n1")', 'tokio::fs::symlink(pty.name(), &args.link)')
replace('''            Err(e) => {
                log::error!("Disconnected: {}", e);''', '''            Err(e) => {
                if args.once { return Err(e); }
                log::error!("Disconnected: {}", e);''')
replace('''            Ok(()) => {
                log::info!("Waiting for device");''', '''            Ok(()) => {
                if args.once { return Ok(()); }
                log::info!("Waiting for device");''')
text += r'''

// A18 Pro binding documented by the pinned public kisd README. The descriptor
// must agree before any UART transmit/portal-enable operations are attempted.
fn neo_descriptor_base(version: u16, descriptor: &[u8]) -> Result<u64, DebugUsbError> {
    if version != 0x400 || descriptor.len() < 40 {
        return Err(DebugUsbError::Read);
    }
    let pointer = u64::from_le_bytes(descriptor[32..40].try_into().unwrap());
    let base = pointer & !0xffffff & !0x1000000;
    if base != 0x348000000 {
        log::error!("NEO_KIS_BINDING_REFUSED version={:04x} descriptor_base=0x{:x}", version, base);
        return Err(DebugUsbError::UnknownBase);
    }
    Ok(base)
}

#[cfg(test)]
mod neo_tests {
    use super::*;
    #[test]
    fn validates_a18_descriptor_and_rejects_other_bindings() {
        let mut descriptor = [0u8; 80];
        descriptor[32..40].copy_from_slice(&0x348123456u64.to_le_bytes());
        assert_eq!(neo_descriptor_base(0x400, &descriptor).unwrap(), 0x348000000);
        assert!(neo_descriptor_base(0x500, &descriptor).is_err());
        for len in 0..40 { assert!(neo_descriptor_base(0x400, &descriptor[..len]).is_err()); }
        for pointer in [0, 0x308123456, 0x548712345, u64::MAX] {
            descriptor[32..40].copy_from_slice(&pointer.to_le_bytes());
            assert!(neo_descriptor_base(0x400, &descriptor).is_err());
        }
    }
}
'''
path.write_text(text)
