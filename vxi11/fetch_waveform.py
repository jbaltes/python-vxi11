#!/usr/bin/env python3
"""
fetch_waveform.py
Automated script to fetch waveform data via VXI11 and save as raw binary or .wfm.
Supports: Tektronix TDS5000/7000, DPO70000, MSO4/5/6, and Agilent DSA-X 91604A.
"""

import sys
import argparse
import vxi11
import numpy as np

# Lazy import handling for optional tm-data-types package dependency
TM_DATA_TYPES_AVAILABLE = False
try:
    from tm_data_types import AnalogWaveform, AnalogWaveformMetaInfo, write_file
    TM_DATA_TYPES_AVAILABLE = True
except ImportError:
    pass

def identify_scope_family(idn_string):
    """Parses the *IDN? string to determine the manufacturer and model family."""
    print(f"[INFO] Instrument Identity: {idn_string}")
    idn_upper = idn_string.upper()
    
    if "TEKTRONIX" in idn_upper:
        model = idn_upper.split(",")[1] if "," in idn_upper else idn_upper
        if any(model.startswith(x) for x in ["TDS5", "TDS7", "DPO7"]):
            return "TEK_LEGACY"
        elif any(x in idn_upper for x in ["MSO4", "MSO5", "MSO6"]):
            return "TEK_MODERN"
        return "TEK_GENERIC"
            
    elif "AGILENT" in idn_upper or "KEYSIGHT" in idn_upper:
        if any(x in idn_upper for x in ["91604A", "DSA-X", "DSAX"]):
            return "AGILENT_INFINIUM"
        return "AGILENT_GENERIC"
            
    return "UNKNOWN"

def get_preamble_scaling(instr, family, channel):
    """
    Queries the timing/vertical preamble fields from the hardware setup.
    Returns: (y_mult, y_off, y_zero, x_incr)
    """
    try:
        if "TEK" in family:
            instr.write(f"DATA:SOURCE {channel}")
            # Query standard Tektronix scaling data constants
            y_mult = float(instr.ask("WFMPRE:YMULT?"))
            y_off = float(instr.ask("WFMPRE:YOFF?"))
            y_zero = float(instr.ask("WFMPRE:YZERO?"))
            x_incr = float(instr.ask("WFMPRE:XINCR?"))
            return y_mult, y_off, y_zero, x_incr
        elif "AGILENT" in family:
            agilent_ch = channel.replace("CH", "CHAN")
            instr.write(f"WAVEFORM:SOURCE {agilent_ch}")
            # Query standard Agilent/Keysight preamble sequence block
            preamble = instr.ask("WAVEFORM:PREAMBLE?").split(",")
            # Format index structure maps: [.., x_increment, .., .., y_increment, y_origin, y_reference]
            x_incr = float(preamble[4])
            y_mult = float(preamble[7])
            y_zero = float(preamble[8])
            y_off = float(preamble[9])
            return y_mult, y_off, y_zero, x_incr
    except Exception as e:
        print(f"[WARNING] Scaling extraction failed ({e}). Defaulting to 1.0.")
    return 1.0, 0.0, 0.0, 1.0

def fetch_waveform(ip_address, channel="CH1", save_wfm=False):
    """Connects to the scope, handles scaling configs, and saves data out."""
    if save_wfm and not TM_DATA_TYPES_AVAILABLE:
        print("[ERROR] 'tm-data-types' package not found. Run: pip install tm-data-types")
        return

    print(f"[INFO] Connecting via VXI11 to {ip_address}...")
    try:
        instr = vxi11.Instrument(ip_address)
        idn = instr.ask("*IDN?")
    except Exception as e:
        print(f"[ERROR] Connection failed: {e}")
        return

    family = identify_scope_family(idn)
    if family == "UNKNOWN":
        print("[ERROR] Unsupported instrument family. Exiting.")
        instr.close()
        return

    print(f"[INFO] Detected Model Family Group: {family}")

    # Read scaling values from instrument memory registers
    y_mult, y_off, y_zero, x_incr = get_preamble_scaling(instr, family, channel)

    # -------------------------------------------------------------------------
    # SCPI Configuration Phase (Device Specific Data Widths)
    # -------------------------------------------------------------------------
    if family == "TEK_LEGACY":
        print("[INFO] Setting Tektronix Legacy parameters: 8-bit, RIBinary format.")
        instr.write(f"DATA:SOURCE {channel}")
        instr.write("DATA:ENC RI")
        instr.write("DATA:WIDTH 1")
        numpy_dtype = np.int8

    elif family == "TEK_MODERN":
        print("[INFO] Setting Tektronix Next-Gen parameters: 16-bit, RIBinary format.")
        instr.write(f"DATA:SOURCE {channel}")
        instr.write("DATA:ENC RI")
        instr.write("DATA:WIDTH 2")
        numpy_dtype = np.int16

    elif family == "AGILENT_INFINIUM":
        print("[INFO] Setting Agilent Infiniium parameters: 16-bit WORD, Signed format.")
        agilent_ch = channel.replace("CH", "CHAN")
        instr.write(f"WAVEFORM:SOURCE {agilent_ch}")
        instr.write("WAVEFORM:BYTEORDER LSBFirst")
        instr.write("WAVEFORM:FORMAT WORD")
        numpy_dtype = np.int16
    elif family in ("TEK_GENERIC", "AGILENT_GENERIC"):
        print(f"[WARNING] Unrecognized specific model, using generic 8-bit fallback for family {family}.")
        if "TEK" in family:
            instr.write(f"DATA:SOURCE {channel}")
            instr.write("DATA:ENC RI")
            instr.write("DATA:WIDTH 1")
        else:
            agilent_ch = channel.replace("CH", "CHAN")
            instr.write(f"WAVEFORM:SOURCE {agilent_ch}")
            instr.write("WAVEFORM:BYTEORDER LSBFirst")
            instr.write("WAVEFORM:FORMAT BYTE")
        numpy_dtype = np.int8

    # -------------------------------------------------------------------------
    # Data Read Phase (IEEE-488.2 Definite Length Block Transfer)
    # -------------------------------------------------------------------------
    print(f"[INFO] Querying raw curve payload from {channel}...")
    try:
        if "TEK" in family:
            instr.write("CURVE?")
            raw_block = instr.read_raw()
        elif "AGILENT" in family:
            instr.write("WAVEFORM:DATA?")
            raw_block = instr.read_raw()

        # Decode definite length headers (#N<length><bytes>)
        if raw_block[0:1] != b'#':
            raise ValueError("Invalid binary block response returned from scope.")
            
        header_digits = int(raw_block[1:2].decode('ascii'))
        data_length = int(raw_block[2:2 + header_digits].decode('ascii'))
        raw_data = raw_block[2 + header_digits : 2 + header_digits + data_length]

        print(f"[SUCCESS] Received {len(raw_data)} bytes of raw waveform data.")
        waveform_array = np.frombuffer(raw_data, dtype=numpy_dtype)

        # -------------------------------------------------------------------------
        # Storage Selection Phase (.bin vs .wfm via tm-data-types)
        # -------------------------------------------------------------------------
        if save_wfm:
            output_filename = f"waveform_{channel}.wfm"
            print(f"[INFO] Initializing AnalogWaveform object wrapper...")

            # Pack inside an AnalogWaveform data container object.
            # IMPORTANT: tm_data_types wants the RAW integer samples in
            # y_axis_values, plus the scale/offset fields separately -
            # it does the YOFF/YMULT/YZERO math itself when the file is
            # read back. Do NOT pre-scale to physical volts here, and do
            # NOT use "y_values" - that attribute doesn't exist on
            # AnalogWaveform, so it was silently getting thrown away and
            # write_file() choked on the still-empty real field.
            wfm_object = AnalogWaveform()
            wfm_object.meta_info = AnalogWaveformMetaInfo()
            wfm_object.y_axis_values = waveform_array          # raw ADC codes
            type_info = np.iinfo(numpy_dtype)
            type_range = int(type_info.max) - int(type_info.min)
            wfm_object.y_axis_extent_magnitude = y_mult * type_range
            wfm_object.y_axis_offset = y_zero                  # == YZERO
            wfm_object.x_axis_spacing = x_incr
            wfm_object.source_name = channel

            # Serialize the unified object model to disk using the writer utility
            write_file(output_filename, wfm_object)
            print(f"[SUCCESS] Native .wfm file safely generated via tm-data-types: '{output_filename}'")
        else:
            output_filename = f"raw_waveform_{channel}.bin"
            waveform_array.tofile(output_filename)
            print(f"[SUCCESS] Raw uncompressed array saved to: '{output_filename}'")

    except Exception as e:
        print(f"[ERROR] Failed to execute trace data block transfer pipeline: {e}")
    finally:
        instr.close()
        print("[INFO] VXI11 Session terminated cleanly.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Acquire and save scope waveform logs.")
    parser.add_argument("ip", help="IP address of the target oscilloscope.")
    parser.add_argument("--ch", default="CH1", help="Target source channel to read out (e.g. CH1, CH2).")
    parser.add_argument("--wfm", action="store_true", help="Save directly into Tektronix .wfm format via tm-data-types.")
    
    args = parser.parse_args()
    fetch_waveform(args.ip, args.ch, args.wfm)
