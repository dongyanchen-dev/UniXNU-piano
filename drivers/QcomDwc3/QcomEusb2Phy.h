/* SPDX-License-Identifier: GPL-2.0-only
 * SM8750 (Xiaomi Pad 8 Pro, piano) M31 eUSB2 PHY and PMIH010x repeater bring-up sequences, as in Linux drivers/phy/qualcomm/
 * phy-qcom-m31-eusb2.c (m31eusb2_phy_init) and drivers/phy/qualcomm/phy-qcom-eusb2-repeater.c. The reference is TCSR_USB2_CLKREF_EN of
 * the TCSR CC block at 0xf204008 (+0x2000), whose parent is xo_board 76.8 MHz divided by 2, so FSEL stays 38.4 MHz as on sheng.
 *
 * This file replaces sheng's QcomEusb2Phy.h. sheng's table is phy-snps-eusb2.c (a different register set: PLL divider registers 0x5c/0x60/
 * 0x68/0x6c/0x70/0x78/0x7c and APB_ACCESS_CMD 0x130); piano is qcom,usb-m31-eusb2-phy (live node hsphy@88e3000, DTB
 * compatible "qcom,usb-m31-eusb2-phy"), which programs 0x16c/0x17c/0x168/0x15c overrides and never touches a PLL divider. */
#ifndef QCOM_EUSB2_PHY_H
#define QCOM_EUSB2_PHY_H
#include <stdint.h>
struct QcomMaskedWrite {uint16_t offset; uint8_t mask, value;};
/* Order of m31eusb2_phy_init(): setup_seq, the FSEL field of COMMON0 (FSEL_38_4_MHZ_VAL 0x6), override_seq, reset_seq. Values are the
 * pre-shifted ones Linux writes (write_readback(off, mask, val << __ffs(mask))): FSEL is bits 6:4, HSTX_PE 3:2, HSTX_SWING 3:0,
 * HSTX_SLEW 2:0, PLL_LOCK_TIME 1:0. The vdd/vdda12 regulators and the 0x12000 PHY BCR are handled by QcomDwc3.cpp. */
static const struct QcomMaskedWrite kQcomEusb2Init[] = {
    /* setup */
    {0x94, 0x02, 0x02},                 /* CFG0: UTMI_PHY_CMN_CTRL_OVERRIDE_EN */
    {0x50, 0x02, 0x02},                 /* UTMI_CTRL5: POR */
    {0x54, 0x01, 0x01},                 /* HS_PHY_CTRL_COMMON0: PHY_ENABLE */
    {0x154, 0x01, 0x00},                /* CFG1: PLL_EN */
    {0xb8, 0x01, 0x01},                 /* FSEL_SEL */
    {0x54, 0x70, 0x60},                 /* COMMON0: FSEL 38.4 MHz (0x6 << 4) */
    /* override */
    {0x16c, 0x0c, 0x00},                /* XCFGI_39_32: HSTX_PE */
    {0x17c, 0x0f, 0x07},                /* XCFGI_71_64: HSTX_SWING */
    {0x168, 0x07, 0x00},                /* XCFGI_31_24: HSTX_SLEW */
    {0x15c, 0x03, 0x00},                /* XCFGI_7_0: PLL_LOCK_TIME */
    /* reset */
    {0x64, 0x08, 0x08},                 /* HS_PHY_CTRL2: USB2_SUSPEND_N_SEL */
    {0x64, 0x04, 0x04},                 /* HS_PHY_CTRL2: USB2_SUSPEND_N */
    {0x3c, 0x01, 0x01},                 /* UTMI_CTRL0: SLEEPM */
    {0x54, 0x02, 0x02},                 /* COMMON0: SIDDQ_SEL */
    {0x54, 0x04, 0x00},                 /* COMMON0: SIDDQ */
    {0x50, 0x02, 0x00},                 /* UTMI_CTRL5: POR */
    {0x64, 0x08, 0x00},                 /* HS_PHY_CTRL2: USB2_SUSPEND_N_SEL */
    {0x94, 0x02, 0x00},                 /* CFG0: UTMI_PHY_CMN_CTRL_OVERRIDE_EN */
};
/* PMIH010x repeater, offsets from its peripheral base (SID 7, 0xfd00, live node c42d000.qcom,spmi:qcom,pmih010x@7:eusb2-repeater@fd00).
 * The tuning table is the piano DTB's qcom,param-override-seq (registers 0x50 to 0x5b, twelve values), not sheng's PM8550B three writes. */
enum {kQcomRepeaterStatus = 0x08, kQcomRepeaterOk = 0x80, kQcomRepeaterEnable = 0x46, kQcomRepeaterEnableBit = 0x80,
      kQcomRepeaterForceEn5 = 0xe8, kQcomRepeaterForceVal5 = 0xed};
static const struct {uint8_t offset, value;} kQcomRepeaterTune[] = {
    {0x50, 0x00}, {0x51, 0x0e}, {0x52, 0x01}, {0x53, 0x07}, {0x54, 0x03}, {0x55, 0x03},
    {0x56, 0x00}, {0x57, 0x06}, {0x58, 0x02}, {0x59, 0x03}, {0x5a, 0x01}, {0x5b, 0x02}};
#endif
