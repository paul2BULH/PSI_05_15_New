import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
import json
import io
import re # Import regex module
from enum import Enum

# Set Streamlit page configuration
st.set_page_config(page_title="Enhanced PSI Web Debugger (PSI 05-15)", layout="wide")
st.title("🏥 Enhanced PSI 05–15 Analyzer + Debugger")
st.markdown("*Comprehensive Patient Safety Indicator Analysis with Advanced Logic*")

# Sidebar for configuration
with st.sidebar:
    st.header("🔧 Configuration")
    debug_mode = st.checkbox("Enable Debug Mode", value=True)
    show_exclusions = st.checkbox("Show Detailed Exclusions", value=True)
    validate_timing = st.checkbox("Enable Timing Validation", value=True)
    
    st.header("🎯 PSI Selection")
    selected_psis = st.multiselect(
        "Select PSIs to Analyze",
        ["PSI_05", "PSI_06", "PSI_07", "PSI_08", "PSI_09", "PSI_10", "PSI_11", "PSI_12", "PSI_13", "PSI_14", "PSI_15"],
        default=["PSI_13", "PSI_14", "PSI_15"]
    )

# Upload input and appendix files
col1, col2 = st.columns(2)
with col1:
    input_file = st.file_uploader("📁 Upload PSI Input Excel", type=[".xlsx"])
with col2:
    # Modified uploader to accept both Excel and JSON for the appendix
    appendix_file = st.file_uploader("📋 Upload PSI Appendix (Excel or JSON)", type=[".xlsx", ".json"])

if input_file and appendix_file:
    try:
        # Load data with progress bar
        with st.spinner("Loading and processing data..."):
            df_input = pd.read_excel(input_file)
            
            # --- Appendix File Loading Logic (Handles both Excel and JSON) ---
            if appendix_file.type == "application/json":
                # For JSON, load directly and convert 'data' key to DataFrame
                json_data = json.load(appendix_file)
                if 'data' in json_data and isinstance(json_data['data'], list):
                    appendix_df = pd.DataFrame(json_data['data'])
                else:
                    st.error("❌ Invalid JSON appendix format. Expected a 'data' key containing a list of objects.")
                    st.stop() # Stop execution if format is incorrect
            else: # Assume .xlsx if not JSON
                appendix_df = pd.read_excel(appendix_file)

        # --- Code Set Extraction (Enhanced to handle descriptive column names) ---
        code_sets = {}
        for col in appendix_df.columns:
            col_clean = str(col).strip() # Ensure column name is string
            # Use regex to extract the code reference from parentheses, e.g., (RECLOIP)
            match = re.search(r'\(([^)]+)\)', col_clean)
            if match:
                # Use the extracted code reference as the key
                code_set_name = f"{match.group(1).upper()}_CODES"
            else:
                # Fallback if no parentheses found (e.g., if appendix column is already clean)
                code_set_name = f"{col_clean.upper()}_CODES"

            # Clean codes: remove periods and convert to uppercase
            codes = appendix_df[col].dropna().astype(str).str.replace(".", "", regex=False).str.upper().tolist()
            code_sets[code_set_name] = codes

        # Add common codes that might not be explicitly listed in the appendix but are used
        # (e.g., ORPROC from Appendix A, SURGI2R from Appendix E, MEDIC2R from Appendix C)
        # Assuming these are provided with their full names in the appendix columns.
        # If not, they would need to be manually added or derived.
        
        # --- Enum for PSI 15 Organ Systems ---
        class OrganSystem(Enum):
            SPLEEN = "spleen"
            ADRENAL = "adrenal"  
            VESSEL = "vessel"
            DIAPHRAGM = "diaphragm"
            GASTROINTESTINAL = "gastrointestinal"
            GENITOURINARY = "genitourinary"

        def build_organ_system_mapping(code_sets):
            """
            Builds a mapping of organ systems to their respective injury and procedure codes for PSI 15.
            This is crucial for the organ-matching logic.
            """
            return {
                OrganSystem.SPLEEN: {
                    'injury_codes': code_sets.get('SPLEEN15D_CODES', []),
                    'procedure_codes': code_sets.get('SPLEEN15P_CODES', [])
                },
                OrganSystem.ADRENAL: {
                    'injury_codes': code_sets.get('ADRENAL15D_CODES', []),
                    'procedure_codes': code_sets.get('ADRENAL15P_CODES', [])
                },
                OrganSystem.VESSEL: {
                    'injury_codes': code_sets.get('VESSEL15D_CODES', []),
                    'procedure_codes': code_sets.get('VESSEL15P_CODES', [])
                },
                OrganSystem.DIAPHRAGM: {
                    'injury_codes': code_sets.get('DIAPHR15D_CODES', []),
                    'procedure_codes': code_sets.get('DIAPHR15P_CODES', [])
                },
                OrganSystem.GASTROINTESTINAL: {
                    'injury_codes': code_sets.get('GI15D_CODES', []),
                    'procedure_codes': code_sets.get('GI15P_CODES', [])
                },
                OrganSystem.GENITOURINARY: {
                    'injury_codes': code_sets.get('GU15D_CODES', []),
                    'procedure_codes': code_sets.get('GU15P_CODES', [])
                }
            }

        organ_systems = build_organ_system_mapping(code_sets)

        # --- Enhanced Data Extraction Functions ---
        def extract_dx_codes_enhanced(row):
            """
            Extracts all diagnosis codes and their POA indicators from a row.
            Returns a list of tuples: (dx_code, poa_status, position, sequence_number).
            Handles up to DX30, including Pdx/Sdx and POA_Sdx naming conventions.
            """
            dx_list = []
            
            # Handle Principal Diagnosis (DX1 or Pdx)
            # Prioritize DX1, then Pdx
            dx1_val = row.get("DX1")
            poa1_val = row.get("POA1")

            if pd.isna(dx1_val) or not str(dx1_val).strip():
                dx1_val = row.get("Pdx")
                # If Pdx is used, need to infer POA for it. Assuming POA1 is for DX1, Pdx might not have a direct POA column.
                # For safety, if Pdx is found but POA1 is not, treat POA as empty (Unknown/Not Applicable).
                # If POA_Sdx1 is present, it might be intended for Pdx if Sdx1 is the first secondary.
                # For now, we'll stick to POA1 for DX1/Pdx and POA_Sdx for Sdx.
                # This part might need further refinement based on exact input file structure.
                pass # poa1_val remains as is, or can be adjusted if a 'POA_Pdx' column exists.
            
            if pd.notna(dx1_val) and str(dx1_val).strip():
                dx_clean = str(dx1_val).replace(".", "").upper().strip()
                poa_clean = str(poa1_val).strip().upper() if pd.notna(poa1_val) else ""
                if poa_clean not in ["Y", "N", "U", "W", ""]:
                    poa_clean = "" # Treat invalid POA as unknown/not applicable
                dx_list.append((dx_clean, poa_clean, "PRINCIPAL", 1))

            # Handle Secondary Diagnoses (DX2-DX30 or Sdx1-Sdx29)
            for i in range(1, 30): # Sdx1 maps to DX2, Sdx29 maps to DX30
                dx_col_name_standard = f"DX{i+1}"
                poa_col_name_standard = f"POA{i+1}"
                dx_col_name_alt = f"Sdx{i}"
                poa_col_name_alt = f"POA_Sdx{i}"

                dx_val = row.get(dx_col_name_standard)
                poa_val = row.get(poa_col_name_standard)

                if pd.isna(dx_val) or not str(dx_val).strip(): # If standard DX column is empty or missing
                    dx_val = row.get(dx_col_name_alt)
                    poa_val = row.get(poa_col_name_alt) # Use alt POA column if alt DX column is used

                if pd.notna(dx_val) and str(dx_val).strip():
                    dx_clean = str(dx_val).replace(".", "").upper().strip()
                    poa_clean = str(poa_val).strip().upper() if pd.notna(poa_val) else ""
                    if poa_clean not in ["Y", "N", "U", "W", ""]:
                        poa_clean = ""
                    dx_list.append((dx_clean, poa_clean, "SECONDARY", i + 1))
            return dx_list

        def extract_proc_info_enhanced(row):
            """
            Extracts all procedure codes and their dates from a row.
            Returns a list of tuples: (proc_code, proc_datetime, sequence_number).
            Handles up to Proc20.
            """
            proc_list = []
            for i in range(1, 21):  # Support up to 20 procedures
                code = row.get(f"Proc{i}")
                date = row.get(f"Proc{i}_Date")
                time = row.get(f"Proc{i}_Time") # Assuming time might be in a separate column
                if pd.notna(code) and str(code).strip():
                    code_clean = str(code).replace(".", "").upper().strip()
                    proc_dt = None
                    if pd.notna(date):
                        try:
                            # Attempt to parse date and time together
                            if pd.notna(time) and str(time).strip():
                                # Handle time as HH:MM:SS or HHMMSS
                                time_str = str(time).strip()
                                if ':' not in time_str and len(time_str) == 6: # Assume HHMMSS format
                                    time_str = f"{time_str[:2]}:{time_str[2:4]}:{time_str[4:]}"
                                elif ':' not in time_str and len(time_str) == 4: # Assume HHMM format
                                    time_str = f"{time_str[:2]}:{time_str[2:]}:00"

                                dt_str = f"{date} {time_str}"
                                proc_dt = pd.to_datetime(dt_str, errors='coerce')
                            else:
                                proc_dt = pd.to_datetime(date, errors='coerce')
                        except Exception as e:
                            # Log error if debug mode is on, but continue gracefully
                            if debug_mode:
                                st.warning(f"Error parsing procedure date/time for Proc{i}: {e}")
                            proc_dt = None # Set to None if parsing fails
                    proc_list.append((code_clean, proc_dt, i))
            return proc_list

        def parse_date_safe(date_input):
            """Safely parse various date formats, returning None on failure."""
            if pd.isna(date_input) or date_input == '':
                return None
            try:
                # Try common formats, coerce errors to NaT (Not a Time)
                return pd.to_datetime(date_input, errors='coerce')
            except:
                return None # Fallback for unexpected errors

        def is_code_in_dx_list(dx_list, codes_to_check, position=None, poa=None):
            """
            Helper to check if any diagnosis code from `codes_to_check` exists in `dx_list`
            with optional `position` (PRINCIPAL/SECONDARY) and `poa` (Y/N/U/W).
            """
            for dx_code, dx_poa, dx_pos, _ in dx_list:
                if dx_code in codes_to_check:
                    if position and dx_pos != position:
                        continue
                    if poa and dx_poa != poa:
                        continue
                    return True
            return False

        def get_matching_dx_info(dx_list, codes_to_check, position=None, poa=None):
            """
            Helper to retrieve matching diagnosis info.
            Returns a list of (dx_code, poa_status, position, sequence_number) tuples.
            """
            matches = []
            for dx_code, dx_poa, dx_pos, dx_seq in dx_list:
                if dx_code in codes_to_check:
                    if position and dx_pos != position:
                        continue
                    if poa and dx_poa != poa:
                        continue
                    matches.append((dx_code, dx_poa, dx_pos, dx_seq))
            return matches

        def get_first_procedure_date(proc_list, target_codes):
            """Returns the earliest date of any procedure in target_codes from proc_list."""
            valid_procs = [dt for code, dt, _ in proc_list if code in target_codes and dt is not None]
            return min(valid_procs) if valid_procs else None

        def get_last_procedure_date(proc_list, target_codes):
            """Returns the latest date of any procedure in target_codes from proc_list."""
            valid_procs = [dt for code, dt, _ in proc_list if code in target_codes and dt is not None]
            return max(valid_procs) if valid_procs else None

        def has_any_procedure(proc_list, target_codes):
            """Checks if any procedure in target_codes exists in proc_list."""
            return any(code in target_codes for code, _, _ in proc_list)

        def count_procedures_of_type(proc_list, target_codes):
            """Counts occurrences of procedures from target_codes in proc_list."""
            return sum(1 for code, _, _ in proc_list if code in target_codes)

        # --- Risk Adjustment / Stratification Logic (Simplified for demonstration) ---
        # Note: Actual AHRQ risk adjustment requires specific parameter estimates
        # and potentially more granular code lists not provided in the JSON.
        # This implementation focuses on the categorization as described.

        def classify_immune_compromise(dx_list, proc_list, code_sets):
            """
            Classifies a patient's immune compromise level for PSI 13 risk adjustment.
            This is a simplified example based on common conditions.
            """
            # Placeholder codes for demonstration (these would come from a comprehensive appendix)
            SEVERE_IMMUNE_DX = code_sets.get('SEVEREIMMUNED_CODES', []) # e.g., HIV/AIDS, severe combined immunodeficiency
            MODERATE_IMMUNE_DX = code_sets.get('MODERATEIMMUNED_CODES', []) # e.g., chronic steroid use, organ transplant
            MALIGNANCY_DX = code_sets.get('MALIGNANCY_CODES', []) # e.g., leukemia, lymphoma, active cancer
            CHEMO_PROC = code_sets.get('CHEMOTHERAPYP_CODES', []) # e.g., chemotherapy administration
            RADIATION_PROC = code_sets.get('RADIATIONP_CODES', []) # e.g., radiation therapy

            # Check for severe immune compromise
            if is_code_in_dx_list(dx_list, SEVERE_IMMUNE_DX, poa="Y") or \
               is_code_in_dx_list(dx_list, SEVERE_IMMUNE_DX, poa="N"): # Check both POA statuses for risk
                return "severe_immune_compromise"
            
            # Check for moderate immune compromise
            if is_code_in_dx_list(dx_list, MODERATE_IMMUNE_DX, poa="Y") or \
               is_code_in_dx_list(dx_list, MODERATE_IMMUNE_DX, poa="N"):
                return "moderate_immune_compromise"
            
            # Check for malignancy with treatment
            has_malignancy_dx = is_code_in_dx_list(dx_list, MALIGNANCY_DX)
            has_chemo_proc = has_any_procedure(proc_list, CHEMO_PROC)
            has_radiation_proc = has_any_procedure(proc_list, RADIATION_PROC)

            if has_malignancy_dx and (has_chemo_proc or has_radiation_proc):
                return "malignancy_with_treatment"
            
            return "baseline_risk"

        def classify_procedure_complexity_psi15(proc_list, code_sets, index_procedure_date):
            """
            Classifies procedure complexity for PSI 15 risk adjustment based on procedures
            performed on the index abdominopelvic procedure date.
            This is a highly simplified example as 'PClassR' definitions are not provided.
            """
            # Placeholder: In a real scenario, PClassR codes would be mapped to complexity levels.
            # For this example, we'll just count total procedures on index date.
            
            procs_on_index_date = [code for code, dt, _ in proc_list 
                                   if dt and index_procedure_date and dt.date() == index_procedure_date.date()]
            
            num_procs_on_index_date = len(procs_on_index_date)

            if num_procs_on_index_date >= 5: # Arbitrary threshold for high complexity
                return "high_complexity"
            elif num_procs_on_index_date >= 2: # Arbitrary threshold for moderate complexity
                return "moderate_complexity"
            else:
                return "low_complexity"

        # --- Main PSI Evaluation Function ---
        def evaluate_psi_comprehensive(row, psi_name, code_sets, organ_systems, debug_mode=False, validate_timing=True):
            """
            Comprehensive PSI evaluation with detailed logic for all PSIs (05-15).
            This function implements the inclusion, exclusion, numerator, and denominator logic
            as specified in the compiled_psi_data.json.
            """
            enc_id = row.get("EncounterID") or row.get("Encounter_ID") or f"Row_{row.name}"
            age = row.get("Age")
            ms_drg = str(row.get("MS-DRG", "")).strip()
            principal_dx = str(row.get("DX1", "")).replace(".", "").upper().strip() # Use DX1 for principal
            atype = row.get("ATYPE")
            mdc = row.get("MDC")
            # --- DRG handling: Prioritize 'DRG' column, fallback to 'MS-DRG' ---
            drg_value = row.get("DRG")
            if pd.isna(drg_value) or str(drg_value).strip() == "":
                drg_value = row.get("MS-DRG") # Use MS-DRG if DRG column is missing or empty
            
            # Convert to numeric for comparison if possible
            try:
                drg_value = int(drg_value)
            except (ValueError, TypeError):
                drg_value = None # Cannot convert to int, treat as invalid
            # --- End DRG handling ---

            
            # Date fields
            admit_date = parse_date_safe(row.get("admission_date") or row.get("Admission_Date"))
            discharge_date = parse_date_safe(row.get("discharge_date") or row.get("Discharge_Date"))
            length_of_stay = row.get("length_of_stay") or row.get("Length_of_stay")
            
            dx_list = extract_dx_codes_enhanced(row)
            proc_list = extract_proc_info_enhanced(row)
            
            psi_status = "Exclusion"
            rationale = []
            detailed_info = {}
            
            # --- Common Exclusions (Apply to most PSIs) ---
            # Data Quality Exclusions
            if drg_value == 999:
                rationale.append("Data Quality: Ungroupable DRG (999)")
                return psi_status, rationale, detailed_info
            
            required_fields = {
                "SEX": row.get("SEX"), "AGE": age, "DQTR": row.get("DQTR"), 
                "YEAR": row.get("YEAR"), "DX1": row.get("DX1") or row.get("Pdx") # Check for DX1 or Pdx
            }
            if any(pd.isna(v) or str(v).strip() == "" for k, v in required_fields.items()):
                missing_fields = [k for k, v in required_fields.items() if pd.isna(v) or str(v).strip() == ""]
                rationale.append(f"Data Quality: Missing required fields ({', '.join(missing_fields)})")
                return psi_status, rationale, detailed_info

            # MDC 14 & 15 Principal Diagnosis Exclusions (Obstetric & Neonatal)
            # These are generally principal diagnosis exclusions
            if is_code_in_dx_list(dx_list, code_sets.get("MDC14PRINDX_CODES", []), position="PRINCIPAL"):
                rationale.append("Population Exclusion: Principal diagnosis in MDC 14 (Obstetric)")
                return psi_status, rationale, detailed_info
                
            if is_code_in_dx_list(dx_list, code_sets.get("MDC15PRINDX_CODES", []), position="PRINCIPAL"):
                rationale.append("Population Exclusion: Principal diagnosis in MDC 15 (Neonatal)")
                return psi_status, rationale, detailed_info

            # Age Exclusion (General, specific PSIs might override)
            if age < 18:
                rationale.append(f"Age Exclusion: Patient age {age} < 18 years")
                return psi_status, rationale, detailed_info
            
            # --- PSI-Specific Logic ---

            # PSI 05 - Retained Surgical Item or Unretrieved Device Fragment Count
            if psi_name == "PSI_05":
                # Denominator/Population Inclusion
                is_surgical_drg = ms_drg in code_sets.get("SURGI2R_CODES", [])
                is_medical_drg = ms_drg in code_sets.get("MEDIC2R_CODES", [])
                is_obstetric_case = is_code_in_dx_list(dx_list, code_sets.get("MDC14PRINDX_CODES", []), position="PRINCIPAL")

                if not ((age >= 18 and (is_surgical_drg or is_medical_drg)) or is_obstetric_case):
                    rationale.append("Population Exclusion: Not surgical/medical DRG (>=18) or obstetric case (any age)")
                    return psi_status, rationale, detailed_info
                
                # Exclusions
                foreiid_codes = code_sets.get("FOREIID_CODES", [])
                
                # Principal diagnosis of retained surgical item
                if is_code_in_dx_list(dx_list, foreiid_codes, position="PRINCIPAL"):
                    rationale.append("Exclusion: Principal diagnosis of retained surgical item")
                    return psi_status, rationale, detailed_info
                
                # Secondary diagnosis of retained surgical item present on admission
                if is_code_in_dx_list(dx_list, foreiid_codes, position="SECONDARY", poa="Y"):
                    rationale.append("Exclusion: Secondary diagnosis of retained surgical item Present on Admission (POA=Y)")
                    return psi_status, rationale, detailed_info
                
                # Numerator: Secondary diagnosis of retained surgical item (not POA)
                numerator_matches = get_matching_dx_info(dx_list, foreiid_codes, position="SECONDARY", poa="N")
                if numerator_matches:
                    psi_status = "Inclusion"
                    rationale.append(f"Numerator: Retained surgical item found (DX: {numerator_matches[0][0]}, POA: N)")
                    detailed_info["retained_surgical_item_matches"] = [m[0] for m in numerator_matches]
                else:
                    rationale.append("No qualifying retained surgical item diagnosis found for numerator")

            # PSI 06 - Iatrogenic Pneumothorax Rate
            elif psi_name == "PSI_06":
                # Denominator Inclusion
                is_surgical_or_medical = ms_drg in code_sets.get("SURGI2R_CODES", []) or ms_drg in code_sets.get("MEDIC2R_CODES", [])
                if not (age >= 18 and is_surgical_or_medical):
                    rationale.append("Population Exclusion: Not surgical/medical DRG or age < 18")
                    return psi_status, rationale, detailed_info
                
                # Exclusions
                iatptxd_codes = code_sets.get("IATPTXD_CODES", []) # Non-traumatic pneumothorax
                ctraumd_codes = code_sets.get("CTRAUMD_CODES", []) # Chest trauma
                pleurad_codes = code_sets.get("PLEURAD_CODES", []) # Pleural conditions
                thoraip_codes = code_sets.get("THORAIP_CODES", []) # Thoracic surgery procedures
                cardsip_codes = code_sets.get("CARDSIP_CODES", []) # Potentially trans-pleural cardiac procedure

                # Principal diagnosis of non-traumatic pneumothorax
                if is_code_in_dx_list(dx_list, iatptxd_codes, position="PRINCIPAL"):
                    rationale.append("Exclusion: Principal diagnosis of non-traumatic pneumothorax")
                    return psi_status, rationale, detailed_info
                
                # Secondary diagnosis of non-traumatic pneumothorax present on admission
                if is_code_in_dx_list(dx_list, iatptxd_codes, position="SECONDARY", poa="Y"):
                    rationale.append("Exclusion: Secondary diagnosis of non-traumatic pneumothorax POA=Y")
                    return psi_status, rationale, detailed_info
                
                # Any diagnosis of specified chest trauma
                if is_code_in_dx_list(dx_list, ctraumd_codes):
                    rationale.append("Exclusion: Any diagnosis of specified chest trauma")
                    return psi_status, rationale, detailed_info
                
                # Any diagnosis of pleural effusion
                if is_code_in_dx_list(dx_list, pleurad_codes):
                    rationale.append("Exclusion: Any diagnosis of pleural effusion")
                    return psi_status, rationale, detailed_info
                
                # Thoracic surgery or potentially trans-pleural cardiac procedure
                if has_any_procedure(proc_list, thoraip_codes) or has_any_procedure(proc_list, cardsip_codes):
                    rationale.append("Exclusion: Thoracic surgery or trans-pleural cardiac procedure")
                    return psi_status, rationale, detailed_info

                # Numerator: Secondary diagnosis of iatrogenic pneumothorax (not POA)
                # Note: JSON uses IATROID* for numerator, IATPTXD* for exclusions.
                iatroid_codes = code_sets.get("IATROID_CODES", [])
                numerator_matches = get_matching_dx_info(dx_list, iatroid_codes, position="SECONDARY", poa="N")
                
                if numerator_matches:
                    psi_status = "Inclusion"
                    rationale.append(f"Numerator: Iatrogenic pneumothorax found (DX: {numerator_matches[0][0]}, POA: N)")
                    detailed_info["iatrogenic_pneumothorax_matches"] = [m[0] for m in numerator_matches]
                else:
                    rationale.append("No qualifying iatrogenic pneumothorax diagnosis found for numerator")

            # PSI 07 - Central Venous Catheter-Related Bloodstream Infection Rate
            elif psi_name == "PSI_07":
                # Denominator Inclusion
                is_surgical_or_medical = ms_drg in code_sets.get("SURGI2R_CODES", []) or ms_drg in code_sets.get("MEDIC2R_CODES", [])
                is_obstetric_case = is_code_in_dx_list(dx_list, code_sets.get("MDC14PRINDX_CODES", []), position="PRINCIPAL")

                if not ((age >= 18 and is_surgical_or_medical) or is_obstetric_case):
                    rationale.append("Population Exclusion: Not surgical/medical DRG (>=18) or obstetric case (any age)")
                    return psi_status, rationale, detailed_info
                
                # Exclusions
                idtmc3d_codes = code_sets.get("IDTMC3D_CODES", []) # CVC-related BSI
                canceid_codes = code_sets.get("CANCEID_CODES", []) # Cancer
                immunid_codes = code_sets.get("IMMUNID_CODES", []) # Immunocompromised state diagnosis
                immunip_codes = code_sets.get("IMMUNIP_CODES", []) # Immunocompromised state procedure

                # Principal diagnosis of CVC-related BSI
                if is_code_in_dx_list(dx_list, idtmc3d_codes, position="PRINCIPAL"):
                    rationale.append("Exclusion: Principal diagnosis of CVC-related BSI")
                    return psi_status, rationale, detailed_info
                
                # Secondary diagnosis of CVC-related BSI present on admission
                if is_code_in_dx_list(dx_list, idtmc3d_codes, position="SECONDARY", poa="Y"):
                    rationale.append("Exclusion: Secondary diagnosis of CVC-related BSI POA=Y")
                    return psi_status, rationale, detailed_info

                # Length of stay less than 2 days
                if pd.notna(length_of_stay) and length_of_stay < 2:
                    rationale.append(f"Exclusion: Length of stay < 2 days ({length_of_stay} days)")
                    return psi_status, rationale, detailed_info
                
                # Any diagnosis of cancer
                if is_code_in_dx_list(dx_list, canceid_codes):
                    rationale.append("Exclusion: Any diagnosis of cancer")
                    return psi_status, rationale, detailed_info
                
                # Any diagnosis of immunocompromised state OR any procedure for immunocompromised state
                if is_code_in_dx_list(dx_list, immunid_codes) or has_any_procedure(proc_list, immunip_codes):
                    rationale.append("Exclusion: Any diagnosis/procedure for immunocompromised state")
                    return psi_status, rationale, detailed_info

                # Numerator: Secondary diagnosis of CVC-related BSI (not POA)
                numerator_matches = get_matching_dx_info(dx_list, idtmc3d_codes, position="SECONDARY", poa="N")
                
                if numerator_matches:
                    psi_status = "Inclusion"
                    rationale.append(f"Numerator: CVC-related BSI found (DX: {numerator_matches[0][0]}, POA: N)")
                    detailed_info["cvc_bsi_matches"] = [m[0] for m in numerator_matches]
                else:
                    rationale.append("No qualifying CVC-related BSI diagnosis found for numerator")

            # PSI 08 - In-Hospital Fall-Associated Fracture Rate
            elif psi_name == "PSI_08":
                # Denominator Inclusion: Surgical or medical discharges for patients ages 18 years and older
                is_surgical_or_medical = ms_drg in code_sets.get("SURGI2R_CODES", []) or ms_drg in code_sets.get("MEDIC2R_CODES", [])
                if not (age >= 18 and is_surgical_or_medical):
                    rationale.append("Population Exclusion: Not surgical/medical DRG or age < 18")
                    return psi_status, rationale, detailed_info
                
                # Exclusions
                fxid_codes = code_sets.get("FXID_CODES", []) # Any fracture
                prosfxd_codes = code_sets.get("PROSFXID_CODES", []) # Joint prosthesis-associated fracture

                # Principal diagnosis of fracture
                if is_code_in_dx_list(dx_list, fxid_codes, position="PRINCIPAL"):
                    rationale.append("Exclusion: Principal diagnosis of fracture")
                    return psi_status, rationale, detailed_info
                
                # Secondary diagnosis of fracture present on admission
                if is_code_in_dx_list(dx_list, fxid_codes, position="SECONDARY", poa="Y"):
                    rationale.append("Exclusion: Secondary diagnosis of fracture POA=Y")
                    return psi_status, rationale, detailed_info
                
                # Any diagnosis of joint prosthesis-associated fracture
                if is_code_in_dx_list(dx_list, prosfxd_codes):
                    rationale.append("Exclusion: Any diagnosis of joint prosthesis-associated fracture")
                    return psi_status, rationale, detailed_info
                
                # Numerator: Hierarchical Logic
                hip_fx_codes = code_sets.get("HIPFXID_CODES", []) # Hip fracture

                # Check for Hip Fracture (priority)
                hip_fx_matches = get_matching_dx_info(dx_list, hip_fx_codes, position="SECONDARY", poa="N")
                
                if hip_fx_matches:
                    psi_status = "Inclusion"
                    rationale.append(f"Numerator: Hip fracture found (DX: {hip_fx_matches[0][0]}, POA: N)")
                    detailed_info["fracture_type"] = "hip_fracture"
                    detailed_info["hip_fracture_matches"] = [m[0] for m in hip_fx_matches]
                else:
                    # Check for Other Fracture (if no hip fracture)
                    other_fx_matches = get_matching_dx_info(dx_list, fxid_codes, position="SECONDARY", poa="N")
                    # Ensure it's not a hip fracture
                    other_fx_matches = [m for m in other_fx_matches if m[0] not in hip_fx_codes]

                    if other_fx_matches:
                        psi_status = "Inclusion"
                        rationale.append(f"Numerator: Other fracture found (DX: {other_fx_matches[0][0]}, POA: N)")
                        detailed_info["fracture_type"] = "other_fracture"
                        detailed_info["other_fracture_matches"] = [m[0] for m in other_fx_matches]
                    else:
                        rationale.append("No qualifying in-hospital fracture found for numerator")
                
                if psi_status == "Inclusion":
                    detailed_info["overall_fracture"] = True # For overall component

            # PSI 09 - Postoperative Hemorrhage or Hematoma Rate
            elif psi_name == "PSI_09":
                # Denominator Inclusion: Surgical discharges (>=18) with OR procedures
                is_surgical_drg = ms_drg in code_sets.get("SURGI2R_CODES", [])
                or_proc_codes = code_sets.get("ORPROC_CODES", [])
                has_or_procedure = has_any_procedure(proc_list, or_proc_codes)

                if not (age >= 18 and is_surgical_drg and has_or_procedure):
                    rationale.append("Population Exclusion: Not surgical DRG (>=18) or no OR procedure")
                    return psi_status, rationale, detailed_info
                
                # Exclusions
                pohmri2d_codes = code_sets.get("POHMRI2D_CODES", []) # Postoperative hemorrhage/hematoma diagnosis
                hemoth2p_codes = code_sets.get("HEMOTH2P_CODES", []) # Treatment of hemorrhage/hematoma procedure
                coagdid_codes = code_sets.get("COAGDID_CODES", []) # Coagulation disorder diagnosis
                medbleedd_codes = code_sets.get("MEDBLEEDD_CODES", []) # Medication-related coagulopathy diagnosis
                thrombolyticp_codes = code_sets.get("THROMBOLYTICP_CODES", []) # Thrombolytic procedure

                # Principal diagnosis of postoperative hemorrhage or hematoma
                if is_code_in_dx_list(dx_list, pohmri2d_codes, position="PRINCIPAL"):
                    rationale.append("Exclusion: Principal diagnosis of postoperative hemorrhage/hematoma")
                    return psi_status, rationale, detailed_info
                
                # Secondary diagnosis of postoperative hemorrhage or hematoma present on admission
                if is_code_in_dx_list(dx_list, pohmri2d_codes, position="SECONDARY", poa="Y"):
                    rationale.append("Exclusion: Secondary diagnosis of postoperative hemorrhage/hematoma POA=Y")
                    return psi_status, rationale, detailed_info
                
                # Any diagnosis of coagulation disorder
                if is_code_in_dx_list(dx_list, coagdid_codes):
                    rationale.append("Exclusion: Any diagnosis of coagulation disorder")
                    return psi_status, rationale, detailed_info
                
                # Principal diagnosis of medication-related coagulopathy
                if is_code_in_dx_list(dx_list, medbleedd_codes, position="PRINCIPAL"):
                    rationale.append("Exclusion: Principal diagnosis of medication-related coagulopathy")
                    return psi_status, rationale, detailed_info
                
                # Secondary diagnosis of medication-related coagulopathy present on admission
                if is_code_in_dx_list(dx_list, medbleedd_codes, position="SECONDARY", poa="Y"):
                    rationale.append("Exclusion: Secondary diagnosis of medication-related coagulopathy POA=Y")
                    return psi_status, rationale, detailed_info

                # Timing-based exclusions (if dates are available)
                if validate_timing and admit_date:
                    first_or_date = get_first_procedure_date(proc_list, or_proc_codes)
                    first_hemoth2p_date = get_first_procedure_date(proc_list, hemoth2p_codes)
                    first_thrombolyticp_date = get_first_procedure_date(proc_list, thrombolyticp_codes)

                    # Only operating room procedure is for treatment of hemorrhage/hematoma
                    if count_procedures_of_type(proc_list, or_proc_codes) == 1 and \
                       has_any_procedure(proc_list, hemoth2p_codes):
                        rationale.append("Exclusion: Only OR procedure is for hemorrhage/hematoma treatment")
                        return psi_status, rationale, detailed_info
                    
                    # Treatment of hemorrhage/hematoma occurs before first operating room procedure
                    if first_hemoth2p_date and first_or_date and first_hemoth2p_date < first_or_date:
                        rationale.append("Exclusion: Hemorrhage treatment before first OR procedure")
                        return psi_status, rationale, detailed_info
                    
                    # Thrombolytic medication before or same day as first hemorrhage treatment
                    if first_thrombolyticp_date and first_hemoth2p_date and \
                       first_thrombolyticp_date.date() <= first_hemoth2p_date.date():
                        rationale.append("Exclusion: Thrombolytic therapy before/same day as hemorrhage treatment")
                        return psi_status, rationale, detailed_info
                
                # Numerator: Secondary diagnosis of postoperative hemorrhage/hematoma (not POA) AND treatment procedure
                numerator_dx_matches = get_matching_dx_info(dx_list, pohmri2d_codes, position="SECONDARY", poa="N")
                has_treatment_procedure = has_any_procedure(proc_list, hemoth2p_codes)

                if numerator_dx_matches and has_treatment_procedure:
                    # Additional timing check for numerator: treatment must be AFTER primary procedure
                    # If dates are available, ensure treatment is after first OR procedure
                    if validate_timing and first_or_date and first_hemoth2p_date:
                        if first_hemoth2p_date > first_or_date:
                            psi_status = "Inclusion"
                            rationale.append(f"Numerator: Postop hemorrhage/hematoma with treatment (DX: {numerator_dx_matches[0][0]})")
                            detailed_info["hemorrhage_dx_matches"] = [m[0] for m in numerator_dx_matches]
                            detailed_info["has_treatment_procedure"] = True
                        else:
                            rationale.append("Numerator: Hemorrhage treatment procedure occurred before or same day as first OR procedure (timing mismatch)")
                    elif not validate_timing: # If timing validation is off, include if dx and proc exist
                        psi_status = "Inclusion"
                        rationale.append(f"Numerator: Postop hemorrhage/hematoma with treatment (DX: {numerator_dx_matches[0][0]}) (Timing validation off)")
                        detailed_info["hemorrhage_dx_matches"] = [m[0] for m in numerator_dx_matches]
                        detailed_info["has_treatment_procedure"] = True
                    else:
                        rationale.append("Numerator: Missing procedure dates for timing validation")
                elif numerator_dx_matches:
                    rationale.append("Numerator: Postop hemorrhage/hematoma diagnosis found, but no qualifying treatment procedure")
                elif has_treatment_procedure:
                    rationale.append("Numerator: Treatment procedure found, but no qualifying postop hemorrhage/hematoma diagnosis")
                else:
                    rationale.append("No qualifying postop hemorrhage/hematoma diagnosis or treatment procedure found for numerator")

            # PSI 10 - Postoperative Acute Kidney Injury Requiring Dialysis Rate
            elif psi_name == "PSI_10":
                # Denominator Inclusion: Elective surgical discharges (>=18)
                is_elective_surgical_drg = ms_drg in code_sets.get("SURGI2R_CODES", []) and atype == 3
                or_proc_codes = code_sets.get("ORPROC_CODES", [])
                has_or_procedure = has_any_procedure(proc_list, or_proc_codes)

                if not (age >= 18 and is_elective_surgical_drg and has_or_procedure):
                    rationale.append("Population Exclusion: Not elective surgical DRG (>=18) or no OR procedure")
                    return psi_status, rationale, detailed_info
                
                # Exclusions
                physidb_codes = code_sets.get("PHYSIDB_CODES", []) # Acute kidney failure diagnosis
                dialyip_codes = code_sets.get("DIALYIP_CODES", []) # Dialysis procedure
                dialy2p_codes = code_sets.get("DIALY2P_CODES", []) # Dialysis access procedure
                cardiid_codes = code_sets.get("CARDIID_CODES", []) # Cardiac arrest diagnosis
                cardrid_codes = code_sets.get("CARDRID_CODES", []) # Severe cardiac dysrhythmia diagnosis
                shockid_codes = code_sets.get("SHOCKID_CODES", []) # Shock diagnosis
                crenlfd_codes = code_sets.get("CRENLFD_CODES", []) # CKD stage 5 or ESRD diagnosis
                urinaryobsid_codes = code_sets.get("URINARYOBSID_CODES", []) # Urinary tract obstruction diagnosis
                solkidd_codes = code_sets.get("SOLKIDD_CODES", []) # Solitary kidney diagnosis
                pneumphrep_codes = code_sets.get("PNEPHREP_CODES", []) # Partial/total nephrectomy procedure

                # Principal diagnosis of acute kidney failure
                if is_code_in_dx_list(dx_list, physidb_codes, position="PRINCIPAL"):
                    rationale.append("Exclusion: Principal diagnosis of acute kidney failure")
                    return psi_status, rationale, detailed_info
                
                # Secondary diagnosis of acute kidney failure present on admission
                if is_code_in_dx_list(dx_list, physidb_codes, position="SECONDARY", poa="Y"):
                    rationale.append("Exclusion: Secondary diagnosis of acute kidney failure POA=Y")
                    return psi_status, rationale, detailed_info
                
                # Timing-based dialysis exclusions (if dates are available)
                if validate_timing and admit_date:
                    first_or_date = get_first_procedure_date(proc_list, or_proc_codes)
                    first_dialy_date = get_first_procedure_date(proc_list, dialyip_codes)
                    first_dialy2_date = get_first_procedure_date(proc_list, dialy2p_codes)

                    if first_dialy_date and first_or_date and first_dialy_date.date() <= first_or_date.date():
                        rationale.append("Exclusion: Dialysis procedure before or same day as first OR procedure")
                        return psi_status, rationale, detailed_info
                    if first_dialy2_date and first_or_date and first_dialy2_date.date() <= first_or_date.date():
                        rationale.append("Exclusion: Dialysis access procedure before or same day as first OR procedure")
                        return psi_status, rationale, detailed_info
                
                # Cardiac/Shock exclusions (principal or secondary POA)
                cardiac_shock_dx_codes = cardiid_codes + cardrid_codes + shockid_codes
                if is_code_in_dx_list(dx_list, cardiac_shock_dx_codes, position="PRINCIPAL") or \
                   is_code_in_dx_list(dx_list, cardiac_shock_dx_codes, position="SECONDARY", poa="Y"):
                    rationale.append("Exclusion: Principal/POA diagnosis of cardiac arrest, dysrhythmia, or shock")
                    return psi_status, rationale, detailed_info
                
                # Chronic kidney disease stage 5 or ESRD (principal or secondary POA)
                if is_code_in_dx_list(dx_list, crenlfd_codes, position="PRINCIPAL") or \
                   is_code_in_dx_list(dx_list, crenlfd_codes, position="SECONDARY", poa="Y"):
                    rationale.append("Exclusion: Principal/POA diagnosis of CKD stage 5 or ESRD")
                    return psi_status, rationale, detailed_info
                
                # Principal diagnosis of urinary tract obstruction
                if is_code_in_dx_list(dx_list, urinaryobsid_codes, position="PRINCIPAL"):
                    rationale.append("Exclusion: Principal diagnosis of urinary tract obstruction")
                    return psi_status, rationale, detailed_info
                
                # Solitary kidney (POA) with partial or total nephrectomy procedure
                has_sol_kidney_poa = is_code_in_dx_list(dx_list, solkidd_codes, poa="Y")
                has_nephrectomy_proc = has_any_procedure(proc_list, pneumphrep_codes)
                if has_sol_kidney_poa and has_nephrectomy_proc:
                    rationale.append("Exclusion: Solitary kidney (POA) with partial/total nephrectomy")
                    return psi_status, rationale, detailed_info

                # Numerator: Postoperative acute kidney failure (secondary, not POA) AND dialysis procedure
                numerator_dx_matches = get_matching_dx_info(dx_list, physidb_codes, position="SECONDARY", poa="N")
                has_dialysis_procedure = has_any_procedure(proc_list, dialyip_codes)

                if numerator_dx_matches and has_dialysis_procedure:
                    # Additional timing check for numerator: dialysis must be AFTER primary OR procedure
                    if validate_timing and first_or_date and first_dialy_date:
                        if first_dialy_date > first_or_date:
                            psi_status = "Inclusion"
                            rationale.append(f"Numerator: Postop AKI requiring dialysis (DX: {numerator_dx_matches[0][0]})")
                            detailed_info["aki_dx_matches"] = [m[0] for m in numerator_dx_matches]
                            detailed_info["has_dialysis_procedure"] = True
                        else:
                            rationale.append("Numerator: Dialysis procedure occurred before or same day as first OR procedure (timing mismatch)")
                    elif not validate_timing:
                        psi_status = "Inclusion"
                        rationale.append(f"Numerator: Postop AKI requiring dialysis (DX: {numerator_dx_matches[0][0]}) (Timing validation off)")
                        detailed_info["aki_dx_matches"] = [m[0] for m in numerator_dx_matches]
                        detailed_info["has_dialysis_procedure"] = True
                    else:
                        rationale.append("Numerator: Missing procedure dates for timing validation")
                elif numerator_dx_matches:
                    rationale.append("Numerator: AKI diagnosis found, but no qualifying dialysis procedure")
                elif has_dialysis_procedure:
                    rationale.append("Numerator: Dialysis procedure found, but no qualifying AKI diagnosis")
                else:
                    rationale.append("No qualifying postop AKI diagnosis or dialysis procedure found for numerator")

            # PSI 11 - Postoperative Respiratory Failure Rate
            elif psi_name == "PSI_11":
                # Denominator Inclusion: Elective surgical discharges (>=18) with OR procedures
                is_elective_surgical_drg = ms_drg in code_sets.get("SURGI2R_CODES", []) and atype == 3
                or_proc_codes = code_sets.get("ORPROC_CODES", [])
                has_or_procedure = has_any_procedure(proc_list, or_proc_codes)

                if not (age >= 18 and is_elective_surgical_drg and has_or_procedure):
                    rationale.append("Population Exclusion: Not elective surgical DRG (>=18) or no OR procedure")
                    return psi_status, rationale, detailed_info
                
                # Exclusions
                acurf3d_codes = code_sets.get("ACURF3D_CODES", []) # Acute respiratory failure diagnosis (general)
                trachid_codes = code_sets.get("TRACHID_CODES", []) # Tracheostomy diagnosis
                trachip_codes = code_sets.get("TRACHIP_CODES", []) # Tracheostomy procedure
                malhypd_codes = code_sets.get("MALHYPD_CODES", []) # Malignant hyperthermia diagnosis
                neuromd_codes = code_sets.get("NEUROMD_CODES", []) # Neuromuscular disorder diagnosis
                dgneuid_codes = code_sets.get("DGNEUID_CODES", []) # Degenerative neurological disorder diagnosis
                nucranp_codes = code_sets.get("NUCRANP_CODES", []) # Head/neck surgery with airway risk
                presopp_codes = code_sets.get("PRESOPP_CODES", []) # Esophageal surgery
                lungcip_codes = code_sets.get("LUNGCIP_CODES", []) # Lung cancer procedure
                lungtransp_codes = code_sets.get("LUNGTRANSP_CODES", []) # Lung or heart transplant

                # Principal diagnosis of acute respiratory failure
                if is_code_in_dx_list(dx_list, acurf3d_codes, position="PRINCIPAL"):
                    rationale.append("Exclusion: Principal diagnosis of acute respiratory failure")
                    return psi_status, rationale, detailed_info
                
                # Secondary diagnosis of acute respiratory failure present on admission
                if is_code_in_dx_list(dx_list, acurf3d_codes, position="SECONDARY", poa="Y"):
                    rationale.append("Exclusion: Secondary diagnosis of acute respiratory failure POA=Y")
                    return psi_status, rationale, detailed_info
                
                # Any diagnosis of tracheostomy present on admission
                if is_code_in_dx_list(dx_list, trachid_codes, poa="Y"):
                    rationale.append("Exclusion: Any diagnosis of tracheostomy POA=Y")
                    return psi_status, rationale, detailed_info
                
                # Only operating room procedure is tracheostomy
                if count_procedures_of_type(proc_list, or_proc_codes) == 1 and \
                   has_any_procedure(proc_list, trachip_codes):
                    rationale.append("Exclusion: Only OR procedure is tracheostomy")
                    return psi_status, rationale, detailed_info
                
                # Tracheostomy occurs before first operating room procedure
                if validate_timing:
                    first_or_date = get_first_procedure_date(proc_list, or_proc_codes)
                    first_trachip_date = get_first_procedure_date(proc_list, trachip_codes)
                    if first_trachip_date and first_or_date and first_trachip_date < first_or_date:
                        rationale.append("Exclusion: Tracheostomy procedure before first OR procedure")
                        return psi_status, rationale, detailed_info
                
                # Any diagnosis of malignant hyperthermia
                if is_code_in_dx_list(dx_list, malhypd_codes):
                    rationale.append("Exclusion: Any diagnosis of malignant hyperthermia")
                    return psi_status, rationale, detailed_info
                
                # Any diagnosis of neuromuscular disorder present on admission
                if is_code_in_dx_list(dx_list, neuromd_codes, poa="Y"):
                    rationale.append("Exclusion: Any diagnosis of neuromuscular disorder POA=Y")
                    return psi_status, rationale, detailed_info
                
                # Any diagnosis of degenerative neurological disorder present on admission
                if is_code_in_dx_list(dx_list, dgneuid_codes, poa="Y"):
                    rationale.append("Exclusion: Any diagnosis of degenerative neurological disorder POA=Y")
                    return psi_status, rationale, detailed_info
                
                # High-risk surgeries
                high_risk_surgery_codes = nucranp_codes + presopp_codes + lungcip_codes + lungtransp_codes
                if has_any_procedure(proc_list, high_risk_surgery_codes):
                    rationale.append("Exclusion: Patient underwent high-risk surgery (e.g., head/neck, esophageal, lung transplant)")
                    return psi_status, rationale, detailed_info
                
                # MDC 4 - Diseases & Disorders of the Respiratory System
                if mdc == 4:
                    rationale.append("Exclusion: MDC 4 (Respiratory System Disorders)")
                    return psi_status, rationale, detailed_info
                
                # Numerator: ANY of the four criteria
                acurf2d_codes = code_sets.get("ACURF2D_CODES", []) # Acute postprocedural respiratory failure
                pr9672p_codes = code_sets.get("PR9672P_CODES", []) # Mechanical ventilation > 96h
                pr9671p_codes = code_sets.get("PR9671P_CODES", []) # Mechanical ventilation 24-96h
                pr9604p_codes = code_sets.get("PR9604P_CODES", []) # Intubation procedure

                first_or_date = get_first_procedure_date(proc_list, or_proc_codes)
                
                # 1. Acute postprocedural respiratory failure (secondary, not POA)
                crit1_met = is_code_in_dx_list(dx_list, acurf2d_codes, position="SECONDARY", poa="N")
                
                # 2. Prolonged mechanical ventilation > 96 consecutive hours (on/after first major OR procedure)
                crit2_met = False
                if validate_timing and first_or_date:
                    last_pr9672p_date = get_last_procedure_date(proc_list, pr9672p_codes)
                    if last_pr9672p_date and last_pr9672p_date >= first_or_date:
                        crit2_met = True
                elif not validate_timing and has_any_procedure(proc_list, pr9672p_codes):
                    crit2_met = True # Conservative if timing validation off

                # 3. Mechanical ventilation 24-96 consecutive hours (2+ days after first major OR procedure)
                crit3_met = False
                if validate_timing and first_or_date:
                    last_pr9671p_date = get_last_procedure_date(proc_list, pr9671p_codes)
                    if last_pr9671p_date and last_pr9671p_date >= (first_or_date + timedelta(days=2)):
                        crit3_met = True
                elif not validate_timing and has_any_procedure(proc_list, pr9671p_codes):
                    crit3_met = True # Conservative if timing validation off

                # 4. Postoperative intubation (1+ days after first major OR procedure)
                crit4_met = False
                if validate_timing and first_or_date:
                    last_pr9604p_date = get_last_procedure_date(proc_list, pr9604p_codes)
                    if last_pr9604p_date and last_pr9604p_date >= (first_or_date + timedelta(days=1)):
                        crit4_met = True
                elif not validate_timing and has_any_procedure(proc_list, pr9604p_codes):
                    crit4_met = True # Conservative if timing validation off

                if crit1_met or crit2_met or crit3_met or crit4_met:
                    psi_status = "Inclusion"
                    rationale.append("Numerator: Patient meets at least one postoperative respiratory complication criterion.")
                    detailed_info["crit1_met"] = crit1_met
                    detailed_info["crit2_met"] = crit2_met
                    detailed_info["crit3_met"] = crit3_met
                    detailed_info["crit4_met"] = crit4_met
                else:
                    rationale.append("No qualifying postoperative respiratory failure criteria met for numerator.")

            # PSI 12 - Perioperative Pulmonary Embolism or Deep Vein Thrombosis Rate
            elif psi_name == "PSI_12":
                # Denominator Inclusion: Surgical discharges (>=18) with OR procedures
                is_surgical_drg = ms_drg in code_sets.get("SURGI2R_CODES", [])
                or_proc_codes = code_sets.get("ORPROC_CODES", [])
                has_or_procedure = has_any_procedure(proc_list, or_proc_codes)

                if not (age >= 18 and is_surgical_drg and has_or_procedure):
                    rationale.append("Population Exclusion: Not surgical DRG (>=18) or no OR procedure")
                    return psi_status, rationale, detailed_info
                
                # Exclusions
                deepvib_codes = code_sets.get("DEEPVIB_CODES", []) # Proximal DVT diagnosis
                pulmoid_codes = code_sets.get("PULMOID_CODES", []) # Pulmonary embolism diagnosis
                hitd_codes = code_sets.get("HITD_CODES", []) # Heparin-induced thrombocytopenia diagnosis
                neurtrad_codes = code_sets.get("NEURTRAD_CODES", []) # Acute brain or spinal injury diagnosis
                venacip_codes = code_sets.get("VENACIP_CODES", []) # Interruption of vena cava procedure
                thromp_codes = code_sets.get("THROMP_CODES", []) # Pulmonary arterial/dialysis access thrombectomy procedure
                ecmop_codes = code_sets.get("ECMOP_CODES", []) # ECMO procedure

                # Principal diagnosis of proximal DVT or PE
                if is_code_in_dx_list(dx_list, deepvib_codes, position="PRINCIPAL") or \
                   is_code_in_dx_list(dx_list, pulmoid_codes, position="PRINCIPAL"):
                    rationale.append("Exclusion: Principal diagnosis of DVT or PE")
                    return psi_status, rationale, detailed_info
                
                # Secondary diagnosis of proximal DVT or PE present on admission
                if is_code_in_dx_list(dx_list, deepvib_codes, position="SECONDARY", poa="Y") or \
                   is_code_in_dx_list(dx_list, pulmoid_codes, position="SECONDARY", poa="Y"):
                    rationale.append("Exclusion: Secondary diagnosis of DVT or PE POA=Y")
                    return psi_status, rationale, detailed_info
                
                # Any secondary diagnosis of heparin-induced thrombocytopenia
                if is_code_in_dx_list(dx_list, hitd_codes, position="SECONDARY"):
                    rationale.append("Exclusion: Secondary diagnosis of heparin-induced thrombocytopenia")
                    return psi_status, rationale, detailed_info
                
                # Any diagnosis of acute brain or spinal injury present on admission
                if is_code_in_dx_list(dx_list, neurtrad_codes, poa="Y"):
                    rationale.append("Exclusion: Any diagnosis of acute brain or spinal injury POA=Y")
                    return psi_status, rationale, detailed_info
                
                # Any procedure for extracorporeal membrane oxygenation (ECMO)
                if has_any_procedure(proc_list, ecmop_codes):
                    rationale.append("Exclusion: Patient underwent ECMO procedure")
                    return psi_status, rationale, detailed_info

                # Timing-based exclusions (if dates are available)
                if validate_timing and admit_date:
                    first_or_date = get_first_procedure_date(proc_list, or_proc_codes)
                    first_venacip_date = get_first_procedure_date(proc_list, venacip_codes)
                    first_thromp_date = get_first_procedure_date(proc_list, thromp_codes)

                    # Interruption of vena cava before or same day as first OR procedure
                    if first_venacip_date and first_or_date and first_venacip_date.date() <= first_or_date.date():
                        rationale.append("Exclusion: Vena cava interruption before/same day as first OR procedure")
                        return psi_status, rationale, detailed_info
                    
                    # Pulmonary arterial/dialysis access thrombectomy before or same day as first OR procedure
                    if first_thromp_date and first_or_date and first_thromp_date.date() <= first_or_date.date():
                        rationale.append("Exclusion: Thrombectomy before/same day as first OR procedure")
                        return psi_status, rationale, detailed_info
                    
                    # Only OR procedure is vena cava interruption and/or thrombectomy
                    all_or_procs = [code for code, _, _ in proc_list if code in or_proc_codes]
                    if all(p in (venacip_codes + thromp_codes) for p in all_or_procs) and len(all_or_procs) > 0:
                        rationale.append("Exclusion: Only OR procedures are vena cava interruption/thrombectomy")
                        return psi_status, rationale, detailed_info

                    # First OR procedure occurs after or on 10th day following admission
                    if first_or_date and (first_or_date - admit_date).days >= 10:
                        rationale.append(f"Exclusion: First OR procedure on/after 10th day of admission (Day {(first_or_date - admit_date).days})")
                        return psi_status, rationale, detailed_info

                # Numerator: Secondary diagnosis of perioperative DVT OR PE (not POA)
                dvt_pe_numerator_codes = deepvib_codes + pulmoid_codes
                numerator_matches = get_matching_dx_info(dx_list, dvt_pe_numerator_codes, position="SECONDARY", poa="N")
                
                if numerator_matches:
                    psi_status = "Inclusion"
                    rationale.append(f"Numerator: Perioperative DVT/PE found (DX: {numerator_matches[0][0]}, POA: N)")
                    detailed_info["dvt_pe_matches"] = [m[0] for m in numerator_matches]
                else:
                    rationale.append("No qualifying perioperative DVT/PE diagnosis found for numerator")

            # PSI 13 - Postoperative Sepsis Rate
            elif psi_name == "PSI_13":
                # Denominator Inclusion: Elective surgical discharges (>=18) with OR procedures
                is_elective_surgical_drg = ms_drg in code_sets.get("SURGI2R_CODES", []) and atype == 3
                or_proc_codes = code_sets.get("ORPROC_CODES", [])
                has_or_procedure = has_any_procedure(proc_list, or_proc_codes)

                if not (age >= 18 and is_elective_surgical_drg and has_or_procedure):
                    rationale.append("Population Exclusion: Not elective surgical DRG (>=18) or no OR procedure")
                    return psi_status, rationale, detailed_info
                
                # Exclusions
                sepsi2d_codes = code_sets.get("SEPTI2D_CODES", []) # Sepsis diagnosis
                infecid_codes = code_sets.get("INFECID_CODES", []) # General infection diagnosis

                # Principal diagnosis of sepsis
                if is_code_in_dx_list(dx_list, sepsi2d_codes, position="PRINCIPAL"):
                    rationale.append("Exclusion: Principal diagnosis of sepsis")
                    return psi_status, rationale, detailed_info
                
                # Secondary diagnosis of sepsis present on admission
                if is_code_in_dx_list(dx_list, sepsi2d_codes, position="SECONDARY", poa="Y"):
                    rationale.append("Exclusion: Secondary diagnosis of sepsis POA=Y")
                    return psi_status, rationale, detailed_info
                
                # Principal diagnosis of infection
                if is_code_in_dx_list(dx_list, infecid_codes, position="PRINCIPAL"):
                    rationale.append("Exclusion: Principal diagnosis of general infection")
                    return psi_status, rationale, detailed_info
                
                # Secondary diagnosis of infection present on admission
                if is_code_in_dx_list(dx_list, infecid_codes, position="SECONDARY", poa="Y"):
                    rationale.append("Exclusion: Secondary diagnosis of general infection POA=Y")
                    return psi_status, rationale, detailed_info
                
                # First OR procedure occurs after or on 10th day following admission
                if validate_timing and admit_date:
                    first_or_date = get_first_procedure_date(proc_list, or_proc_codes)
                    if first_or_date and (first_or_date - admit_date).days >= 10:
                        rationale.append(f"Exclusion: First OR procedure on/after 10th day of admission (Day {(first_or_date - admit_date).days})")
                        return psi_status, rationale, detailed_info

                # Numerator: Secondary diagnosis of postoperative sepsis (not POA)
                numerator_matches = get_matching_dx_info(dx_list, sepsi2d_codes, position="SECONDARY", poa="N")
                
                if numerator_matches:
                    psi_status = "Inclusion"
                    rationale.append(f"Numerator: Postoperative sepsis found (DX: {numerator_matches[0][0]}, POA: N)")
                    detailed_info["sepsis_matches"] = [m[0] for m in numerator_matches]
                else:
                    rationale.append("No qualifying postoperative sepsis diagnosis found for numerator")
                
                # Risk Adjustment for PSI 13 (Categorization only)
                detailed_info["risk_category"] = classify_immune_compromise(dx_list, proc_list, code_sets)
                rationale.append(f"Risk Category: {detailed_info['risk_category']}")

            # PSI 14 - Postoperative Wound Dehiscence Rate
            elif psi_name == "PSI_14":
                # Denominator Inclusion: Abdominopelvic surgery (open or non-open) for patients >=18
                abdomipopen_codes = code_sets.get("ABDOMIPOPEN_CODES", [])
                abdomipother_codes = code_sets.get("ABDOMIPOTHER_CODES", [])
                
                has_open_abdominal = has_any_procedure(proc_list, abdomipopen_codes)
                has_other_abdominal = has_any_procedure(proc_list, abdomipother_codes)
                
                if not (age >= 18 and (has_open_abdominal or has_other_abdominal)):
                    rationale.append("Population Exclusion: Not age >= 18 or no abdominopelvic surgery")
                    return psi_status, rationale, detailed_info
                
                # Exclusions
                recloip_codes = code_sets.get("RECLOIP_CODES", []) # Abdominal wall reclosure procedure
                abwallcd_codes = code_sets.get("ABWALLCD_CODES", []) # Disruption of internal surgical wound diagnosis

                # Principal diagnosis of disruption of internal surgical wound
                if is_code_in_dx_list(dx_list, abwallcd_codes, position="PRINCIPAL"):
                    rationale.append("Exclusion: Principal diagnosis of wound disruption")
                    return psi_status, rationale, detailed_info
                
                # Secondary diagnosis of disruption of internal surgical wound present on admission
                if is_code_in_dx_list(dx_list, abwallcd_codes, position="SECONDARY", poa="Y"):
                    rationale.append("Exclusion: Secondary diagnosis of wound disruption POA=Y")
                    return psi_status, rationale, detailed_info
                
                # Length of stay less than 2 days
                if pd.notna(length_of_stay) and length_of_stay < 2:
                    rationale.append(f"Exclusion: Length of stay < 2 days ({length_of_stay})")
                    return psi_status, rationale, detailed_info
                
                # Timing-based exclusions (reclosure before/same day as initial surgery)
                if validate_timing:
                    first_open_abdom_date = get_first_procedure_date(proc_list, abdomipopen_codes)
                    first_other_abdom_date = get_first_procedure_date(proc_list, abdomipother_codes)
                    last_recloip_date = get_last_procedure_date(proc_list, recloip_codes)

                    if last_recloip_date:
                        if first_open_abdom_date and last_recloip_date.date() <= first_open_abdom_date.date():
                            rationale.append("Exclusion: Reclosure before/same day as first open abdominopelvic surgery")
                            return psi_status, rationale, detailed_info
                        if first_other_abdom_date and last_recloip_date.date() <= first_other_abdom_date.date():
                            rationale.append("Exclusion: Reclosure before/same day as first non-open abdominopelvic surgery")
                            return psi_status, rationale, detailed_info
                
                # Numerator: Has reclosure procedure AND wound disruption diagnosis (not POA)
                has_reclosure_procedure = has_any_procedure(proc_list, recloip_codes)
                wound_disruption_dx_matches = get_matching_dx_info(dx_list, abwallcd_codes, poa="N") # Any position, not POA

                if has_reclosure_procedure and wound_disruption_dx_matches:
                    psi_status = "Inclusion"
                    rationale.append(f"Numerator: Postoperative wound dehiscence (DX: {wound_disruption_dx_matches[0][0]}) with reclosure procedure")
                    detailed_info["has_reclosure_procedure"] = True
                    detailed_info["wound_disruption_dx_matches"] = [m[0] for m in wound_disruption_dx_matches]
                    
                    # Stratification for PSI 14
                    # Priority: Open approach if any open abdominopelvic surgery exists
                    if has_open_abdominal:
                        detailed_info["stratum"] = "open_approach"
                    else:
                        detailed_info["stratum"] = "non_open_approach"
                    rationale.append(f"Stratum: {detailed_info['stratum']}")

                elif has_reclosure_procedure:
                    rationale.append("Numerator: Reclosure procedure found, but no qualifying wound disruption diagnosis")
                elif wound_disruption_dx_matches:
                    rationale.append("Numerator: Wound disruption diagnosis found, but no reclosure procedure")
                else:
                    rationale.append("No qualifying wound dehiscence criteria met for numerator")

            # PSI 15 - Abdominopelvic Accidental Puncture or Laceration Rate
            elif psi_name == "PSI_15":
                # Denominator Inclusion: Surgical or medical discharges (>=18) with abdominopelvic procedures
                is_surgical_or_medical = ms_drg in code_sets.get("SURGI2R_CODES", []) or ms_drg in code_sets.get("MEDIC2R_CODES", [])
                abdomi15p_codes = code_sets.get("ABDOMI15P_CODES", []) # Abdominopelvic procedures (index)
                
                has_abdominopelvic_procedure = has_any_procedure(proc_list, abdomi15p_codes)

                if not (age >= 18 and is_surgical_or_medical and has_abdominopelvic_procedure):
                    rationale.append("Population Exclusion: Not surgical/medical DRG (>=18) or no abdominopelvic procedure")
                    return psi_status, rationale, detailed_info
                
                # Establish index procedure date (first qualifying abdominopelvic procedure)
                index_procedure_date = get_first_procedure_date(proc_list, abdomi15p_codes)
                if not index_procedure_date:
                    rationale.append("Exclusion: Missing index abdominopelvic procedure date")
                    return psi_status, rationale, detailed_info
                
                # Exclusions (General, then organ-specific POA)
                # Principal diagnosis of accidental puncture/laceration for any organ
                all_injury_codes = []
                for os in OrganSystem:
                    all_injury_codes.extend(organ_systems[os]['injury_codes'])

                if is_code_in_dx_list(dx_list, all_injury_codes, position="PRINCIPAL"):
                    rationale.append("Exclusion: Principal diagnosis of accidental puncture/laceration for any organ")
                    return psi_status, rationale, detailed_info
                
                # Numerator: Triple AND logic (Injury DX + Related PROC + Organ Match + Timing)
                qualifying_organs_for_numerator = []
                detailed_info["organ_analysis_results"] = {}

                for organ_system_enum in OrganSystem:
                    organ_info = organ_systems[organ_system_enum]
                    organ_name = organ_system_enum.value

                    # 1. Organ-specific injury diagnosis (secondary, not POA)
                    injury_dx_matches = get_matching_dx_info(dx_list, organ_info['injury_codes'], position="SECONDARY", poa="N")
                    
                    # 2. Related evaluation/treatment procedure within 1-30 days after index procedure
                    related_proc_matches = []
                    for proc_code, proc_dt, _ in proc_list:
                        if proc_code in organ_info['procedure_codes'] and proc_dt and index_procedure_date:
                            days_diff = (proc_dt - index_procedure_date).days
                            if 1 <= days_diff <= 30: # Window is 1 to 30 days
                                related_proc_matches.append((proc_code, proc_dt, days_diff))
                    
                    # 3. Organ matching: injury diagnosis and related procedure must be for the same organ system
                    # This is implicitly handled by iterating through organ_systems and checking their specific codes.
                    
                    # Organ-specific POA exclusion check (before numerator inclusion)
                    # Secondary diagnosis of accidental puncture/laceration present on admission with matching related procedure
                    poa_injury_matches = get_matching_dx_info(dx_list, organ_info['injury_codes'], position="SECONDARY", poa="Y")
                    
                    is_excluded_by_poa = False
                    if poa_injury_matches and related_proc_matches:
                        rationale.append(f"Exclusion: POA injury ({poa_injury_matches[0][0]}) with matching related procedure for {organ_name}")
                        is_excluded_by_poa = True
                        
                    detailed_info["organ_analysis_results"][organ_name] = {
                        "has_injury_dx": len(injury_dx_matches) > 0,
                        "has_related_proc_in_window": len(related_proc_matches) > 0,
                        "is_poa_excluded": is_excluded_by_poa
                    }

                    if injury_dx_matches and related_proc_matches and not is_excluded_by_poa:
                        qualifying_organs_for_numerator.append(organ_name)
                
                if qualifying_organs_for_numerator:
                    psi_status = "Inclusion"
                    rationale.append(f"Numerator: Accidental puncture/laceration found for organs: {', '.join(qualifying_organs_for_numerator)}")
                    detailed_info["qualifying_organs"] = qualifying_organs_for_numerator
                else:
                    rationale.append("No qualifying accidental puncture/laceration (injury + procedure + timing + organ match) found for numerator")
                
                # Risk Adjustment for PSI 15 (Categorization only)
                detailed_info["risk_category"] = classify_procedure_complexity_psi15(proc_list, code_sets, index_procedure_date)
                rationale.append(f"Risk Category: {detailed_info['risk_category']}")

            else:
                rationale.append(f"PSI {psi_name} logic not yet fully implemented or recognized.")

            return psi_status, rationale, detailed_info

        # --- Main Analysis Loop ---
        all_psi_results_dfs = [] # List to store DataFrames for each PSI
        if selected_psis:
            for psi in selected_psis:
                st.subheader(f"📊 {psi} Analysis Results")
                
                # Create columns for metrics
                col1, col2, col3, col4 = st.columns(4)
                
                # Initialize counters
                inclusions = 0
                exclusions = 0
                total_cases = len(df_input)
                
                # Detailed results storage
                detailed_results = []
                
                # Process each row
                progress_bar = st.progress(0)
                for idx, row in df_input.iterrows():
                    progress_bar.progress((idx + 1) / total_cases)
                    
                    status, rationale, detailed_info = evaluate_psi_comprehensive(
                        row, psi, code_sets, organ_systems, debug_mode=debug_mode, validate_timing=validate_timing
                    )
                    
                    if status == "Inclusion":
                        inclusions += 1
                    else:
                        exclusions += 1
                    
                    # Store detailed results
                    result_record = {
                        "EncounterID": row.get("EncounterID") or row.get("Encounter_ID") or f"Row_{idx}",
                        "PSI": psi, # Add PSI name to the record
                        "Status": status,
                        "Rationale": "; ".join(rationale),
                        "Age": row.get("Age", ""),
                        "MS_DRG": row.get("MS-DRG", ""),
                        "PrincipalDX": row.get("DX1", "") or row.get("Pdx", ""), # Use DX1 or Pdx for consistency
                        "ATYPE": row.get("ATYPE", ""),
                        "Length_of_Stay": row.get("length_of_stay") or row.get("Length_of_stay", "")
                    }
                    
                    # Add PSI-specific details
                    if detailed_info:
                        for key, value in detailed_info.items():
                            # Convert complex objects to string for display
                            if isinstance(value, (list, dict, Enum)):
                                result_record[f"Detail_{key}"] = str(value)
                            else:
                                result_record[f"Detail_{key}"] = value
                    
                    detailed_results.append(result_record)
                
                progress_bar.empty()
                
                # Display metrics
                with col1:
                    st.metric("Total Cases", total_cases)
                with col2:
                    st.metric("Inclusions", inclusions, delta=f"{(inclusions/total_cases*100):.1f}%" if total_cases > 0 else "0.0%")
                with col3:
                    st.metric("Exclusions", exclusions, delta=f"{(exclusions/total_cases*100):.1f}%" if total_cases > 0 else "0.0%")
                with col4:
                    rate = (inclusions / total_cases * 1000) if total_cases > 0 else 0
                    st.metric("Rate per 1000", f"{rate:.2f}")
                
                # Results DataFrame for current PSI
                results_df = pd.DataFrame(detailed_results)
                all_psi_results_dfs.append(results_df) # Add to the list for overall download
                
                # Filter options
                col1, col2 = st.columns(2)
                with col1:
                    status_filter = st.selectbox(f"Filter by Status ({psi})", 
                                               ["All", "Inclusion", "Exclusion"], 
                                               key=f"status_{psi}")
                with col2:
                    show_details = st.checkbox(f"Show Detailed Columns ({psi})", 
                                             value=False, key=f"details_{psi}")
                
                # Apply filters
                filtered_df = results_df.copy()
                if status_filter != "All":
                    filtered_df = filtered_df[filtered_df["Status"] == status_filter]
                
                # Select columns to display
                if show_details:
                    display_cols = list(filtered_df.columns)
                else:
                    # Default columns for display
                    display_cols = ["EncounterID", "Status", "Rationale", "Age", "MS_DRG", "PrincipalDX", "ATYPE", "Length_of_Stay"]
                    display_cols = [col for col in display_cols if col in filtered_df.columns] # Ensure column exists
                
                # Display results table
                st.dataframe(
                    filtered_df[display_cols],
                    use_container_width=True,
                    height=400
                )
                
                # Download options for individual PSI results
                col1, col2 = st.columns(2)
                with col1:
                    csv_data = filtered_df.to_csv(index=False)
                    st.download_button(
                        f"📥 Download {psi} Results (CSV)",
                        csv_data,
                        f"{psi}_results.csv",
                        "text/csv"
                    )
                
                with col2:
                    # Create Excel buffer
                    excel_buffer = io.BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                        filtered_df.to_excel(writer, sheet_name=f'{psi}_Results', index=False)
                    excel_data = excel_buffer.getvalue()
                    
                    st.download_button(
                        f"📥 Download {psi} Results (Excel)",
                        excel_data,
                        f"{psi}_results.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                
                # Debug information
                if debug_mode:
                    with st.expander(f"🔍 Debug Information for {psi}"):
                        st.write("**Code Sets Used (Count of codes):**")
                        # Dynamically list all code sets used by this PSI
                        psi_code_references = {
                            "PSI_05": ["FOREIID_CODES", "SURGI2R_CODES", "MEDIC2R_CODES", "MDC14PRINDX_CODES", "MDC15PRINDX_CODES"],
                            "PSI_06": ["IATROID_CODES", "IATPTXD_CODES", "CTRAUMD_CODES", "PLEURAD_CODES", "THORAIP_CODES", "CARDSIP_CODES", "SURGI2R_CODES", "MEDIC2R_CODES", "MDC14PRINDX_CODES", "MDC15PRINDX_CODES"],
                            "PSI_07": ["IDTMC3D_CODES", "CANCEID_CODES", "IMMUNID_CODES", "IMMUNIP_CODES", "SURGI2R_CODES", "MEDIC2R_CODES", "MDC14PRINDX_CODES", "MDC15PRINDX_CODES"],
                            "PSI_08": ["FXID_CODES", "HIPFXID_CODES", "PROSFXID_CODES", "SURGI2R_CODES", "MEDIC2R_CODES", "MDC14PRINDX_CODES", "MDC15PRINDX_CODES"],
                            "PSI_09": ["POHMRI2D_CODES", "HEMOTH2P_CODES", "COAGDID_CODES", "MEDBLEEDD_CODES", "THROMBOLYTICP_CODES", "ORPROC_CODES", "SURGI2R_CODES", "MDC14PRINDX_CODES", "MDC15PRINDX_CODES"],
                            "PSI_10": ["PHYSIDB_CODES", "DIALYIP_CODES", "DIALY2P_CODES", "CARDIID_CODES", "CARDRID_CODES", "SHOCKID_CODES", "CRENLFD_CODES", "URINARYOBSID_CODES", "SOLKIDD_CODES", "PNEPHREP_CODES", "ORPROC_CODES", "SURGI2R_CODES", "MDC14PRINDX_CODES", "MDC15PRINDX_CODES"],
                            "PSI_11": ["ACURF2D_CODES", "ACURF3D_CODES", "PR9672P_CODES", "PR9671P_CODES", "PR9604P_CODES", "TRACHID_CODES", "TRACHIP_CODES", "MALHYPD_CODES", "NEUROMD_CODES", "DGNEUID_CODES", "NUCRANP_CODES", "PRESOPP_CODES", "LUNGCIP_CODES", "LUNGTRANSP_CODES", "ORPROC_CODES", "SURGI2R_CODES", "MDC14PRINDX_CODES", "MDC15PRINDX_CODES"],
                            "PSI_12": ["DEEPVIB_CODES", "PULMOID_CODES", "HITD_CODES", "NEURTRAD_CODES", "VENACIP_CODES", "THROMP_CODES", "ECMOP_CODES", "ORPROC_CODES", "SURGI2R_CODES", "MEDIC2R_CODES", "MDC14PRINDX_CODES", "MDC15PRINDX_CODES"],
                            "PSI_13": ["SEPTI2D_CODES", "INFECID_CODES", "ORPROC_CODES", "SURGI2R_CODES", "MDC14PRINDX_CODES", "MDC15PRINDX_CODES", "SEVEREIMMUNED_CODES", "MODERATEIMMUNED_CODES", "MALIGNANCY_CODES", "CHEMOTHERAPYP_CODES", "RADIATIONP_CODES"], # Added risk adjustment codes
                            "PSI_14": ["RECLOIP_CODES", "ABWALLCD_CODES", "ABDOMIPOPEN_CODES", "ABDOMIPOTHER_CODES", "MDC14PRINDX_CODES", "MDC15PRINDX_CODES"],
                            "PSI_15": ["ABDOMI15P_CODES", "SPLEEN15D_CODES", "SPLEEN15P_CODES", "ADRENAL15D_CODES", "ADRENAL15P_CODES", "VESSEL15D_CODES", "VESSEL15P_CODES", "DIAPHR15D_CODES", "DIAPHR15P_CODES", "GI15D_CODES", "GI15P_CODES", "GU15D_CODES", "GU15P_CODES", "SURGI2R_CODES", "MEDIC2R_CODES", "MDC14PRINDX_CODES", "MDC15PRINDX_CODES"]
                        }
                        
                        codes_for_psi = psi_code_references.get(psi, [])
                        for code_type in codes_for_psi:
                            st.write(f"- {code_type}: {len(code_sets.get(code_type, []))} codes")
                
                st.divider()
        
            # --- Overall Results Download Button (after all PSI analyses) ---
            if all_psi_results_dfs:
                combined_results_df = pd.concat(all_psi_results_dfs, ignore_index=True)
                
                # Create a single Excel file with all PSI results on one sheet
                output_excel_buffer = io.BytesIO()
                with pd.ExcelWriter(output_excel_buffer, engine='openpyxl') as writer:
                    combined_results_df.to_excel(writer, sheet_name='All_PSI_Results', index=False)
                output_excel_bytes = output_excel_buffer.getvalue()

                st.markdown("---") # Separator for the overall download button
                st.subheader("⬇️ Download All PSI Analysis Results")
                st.download_button(
                    "📥 Download All Results (Excel)",
                    data=output_excel_bytes,
                    file_name="All_PSI_Results.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            # --- End Overall Results Download Button ---

        else:
            st.warning("⚠️ Please select at least one PSI to analyze.")

    except Exception as e:
        st.error(f"❌ Error processing files: {str(e)}")
        if debug_mode:
            st.exception(e)

else:
    st.info("📤 Please upload both the PSI Input Excel file and PSI Appendix (Excel or JSON) file to begin analysis.")
    
    # Show sample data format
    with st.expander("📋 Expected Data Format"):
        st.markdown("""
        **Input Excel File should contain columns like:**
        - EncounterID or Encounter_ID (Unique identifier for each patient encounter)
        - Age (Patient's age in years)
        - MS-DRG (Medicare Severity Diagnosis Related Group)
        - **Pdx** (Principal Diagnosis) or **DX1** (Principal Diagnosis)
        - **Sdx1, Sdx2, ..., Sdx29** (Secondary Diagnosis codes, ICD-10-CM format) or **DX2, DX3, ..., DX30**
        - **POA_Sdx1, POA_Sdx2, ..., POA_Sdx29** (Present on Admission indicators for corresponding secondary diagnoses: Y, N, U, W) or **POA1, POA2, ..., POA30**
        - Proc1, Proc2, ..., Proc20 (Procedure codes, ICD-10-PCS format)
        - Proc1_Date, Proc2_Date, ... (Procedure dates, YYYY-MM-DD format)
        - Proc1_Time, Proc2_Time, ... (Optional: Procedure times, HH:MM:SS or HHMMSS format)
        - admission_date (Patient's admission date, YYYY-MM-DD format)
        - discharge_date (Patient's discharge date, YYYY-MM-DD format)
        - length_of_stay (Calculated length of stay in days)
        - ATYPE (Admission Type: 1=Emergency, 2=Urgent, 3=Elective, 4=Newborn, 5=Not Available)
        - MDC (Major Diagnostic Category)
        - **DRG** (Diagnosis Related Group) or **MS-DRG** (for DRG value if 'DRG' column is absent)
        - SEX, DQTR (Discharge Quarter), YEAR (Discharge Year) - Required for data quality checks.
        
        **Appendix File (Excel or JSON) should contain:**
        - Separate columns (in Excel) or keys (in JSON objects within the 'data' array) for each code set referenced in the PSI definitions (e.g., `FOREIID`, `SURGI2R`, `MEDIC2R`, `SEPTI2D`, `ORPROC`, `SPLEEN15D`, etc.).
        - Each column/key should list the relevant ICD-10-CM or ICD-10-PCS codes.
        - Column names in the Excel appendix or keys in the JSON objects should ideally contain the `code_reference` name in parentheses (e.g., `Abdominopelvic surgery, open approach, procedure codes: (ABDOMIPOPEN)`), or directly be the code reference name (e.g., `ABDOMIPOPEN`).
        
        **Key Data Quality Requirements:**
        - All diagnosis codes should be in ICD-10-CM format (e.g., A000, S36010A). Periods are removed during processing.
        - All procedure codes should be in ICD-10-PCS format (e.g., 001607A). Periods are removed during processing.
        - POA indicators are crucial for accurate PSI calculation.
        - Procedure dates and admission dates are required for timing-sensitive PSIs.
        - ATYPE field is essential for PSIs requiring 'elective' admissions (e.g., PSI 13).
        """)

# Footer
st.markdown("---")
st.markdown(
    """
<div style='text-align: center; color: #666;'>
    <p><strong>Enhanced PSI 05-15 Analyzer</strong> - Advanced Patient Safety Indicator Analysis</p>
    <p>Built with Streamlit • Supports AHRQ PSI v2023 Specifications (based on provided JSON)</p>
    <p><em>For technical support or questions, please refer to AHRQ PSI documentation</em></p>
</div>
""",
    unsafe_allow_html=True,
)