import streamlit as st
import pandas as pd
from io import StringIO, BytesIO
from Bio import SeqIO
import tempfile
import base64

st.set_page_config(layout="wide", page_title="Merge/Add Fields App")

st.title("Merge/Add Fields from One File to Another (Excel/CSV/TXT/FASTA)")

# --- Helper functions -------------------------------------------------------

def read_table(file, file_type, delimiter=",", header_row=0, encoding="utf-8"):
    """Read CSV/TXT/Excel into pandas DataFrame with parsing options."""
    try:
        if file_type in ("csv", "txt"):
            file.seek(0)
            text = file.read().decode(encoding) if isinstance(file.read(0), bytes) else file.read()
            # Reset pointer after reading
            file.seek(0)
            return pd.read_csv(file, sep=delimiter, header=header_row, encoding=encoding, engine="python")
        elif file_type in ("xls", "xlsx"):
            file.seek(0)
            return pd.read_excel(file, header=header_row)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return pd.DataFrame()

def parse_fasta(file):
    """Parse FASTA into DataFrame with columns: accession, description, sequence"""
    # Accept bytes or text
    try:
        file.seek(0)
        # Biopython expects a handle with text; ensure bytes -> text
        content = file.read()
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="ignore")
        handle = StringIO(content)
        records = []
        for rec in SeqIO.parse(handle, "fasta"):
            # accession: try to extract first token of id or from description
            accession = rec.id.split("|")[-1] if "|" in rec.id else rec.id
            records.append({
                "accession": accession,
                "description": rec.description,
                "sequence": str(rec.seq)
            })
        return pd.DataFrame(records)
    except Exception as e:
        st.error(f"Error parsing FASTA: {e}")
        return pd.DataFrame()

def df_preview(df, n=5):
    if df is None or df.empty:
        st.write("No data or empty dataframe.")
    else:
        st.dataframe(df.head(n))

def to_excel_bytes(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()

def download_link(df, filename="merged.xlsx"):
    b = to_excel_bytes(df)
    b64 = base64.b64encode(b).decode()
    href = f'<a href="data:application/octet-stream;base64,{b64}" download="{filename}">Download {filename}</a>'
    return href

# --- UI: Upload files -------------------------------------------------------

st.sidebar.header("1) Upload files")

uploaded_info = st.sidebar.file_uploader(
    "Upload information file (FASTA/CSV/TXT/XLSX) — this will be used to add fields to targets",
    type=["fasta", "fa", "csv", "txt", "xls", "xlsx"],
    accept_multiple_files=False
)

uploaded_targets = st.sidebar.file_uploader(
    "Upload target files (Excel/CSV/TXT) — you can upload multiple",
    type=["csv", "txt", "xls", "xlsx"],
    accept_multiple_files=True
)

st.sidebar.markdown("---")
st.sidebar.header("Parsing defaults")
default_delim = st.sidebar.text_input("Default delimiter for CSV/TXT", value=",")
default_header = st.sidebar.number_input("Default header row index (0-based)", value=0, min_value=0)
default_encoding = st.sidebar.text_input("Default encoding", value="utf-8")

# --- Load info file ---------------------------------------------------------

info_df = None
info_file_type = None
if uploaded_info:
    info_name = uploaded_info.name.lower()
    st.sidebar.write(f"Info file: **{uploaded_info.name}**")
    if info_name.endswith((".fasta", ".fa")):
        info_file_type = "fasta"
        st.sidebar.write("Detected FASTA file.")
        # parsing options for fasta are minimal
        if st.sidebar.button("Preview parsed FASTA"):
            info_df = parse_fasta(uploaded_info)
    elif info_name.endswith((".csv", ".txt")):
        info_file_type = "csv"
        st.sidebar.write("Detected CSV/TXT file.")
        delim = st.sidebar.text_input("Delimiter for info file", value=default_delim, key="info_delim")
        header = st.sidebar.number_input("Header row index for info file", value=default_header, key="info_header", min_value=0)
        enc = st.sidebar.text_input("Encoding for info file", value=default_encoding, key="info_enc")
        if st.sidebar.button("Preview parsed info table"):
            info_df = read_table(uploaded_info, "csv", delimiter=delim, header_row=header, encoding=enc)
    elif info_name.endswith((".xls", ".xlsx")):
        info_file_type = "excel"
        st.sidebar.write("Detected Excel file.")
        header = st.sidebar.number_input("Header row index for info file", value=default_header, key="info_x_header", min_value=0)
        if st.sidebar.button("Preview parsed info table (Excel)"):
            info_df = read_table(uploaded_info, "xlsx", header_row=header)

# If user didn't click preview, still attempt to parse for convenience
if uploaded_info and info_df is None:
    try:
        if info_file_type == "fasta":
            info_df = parse_fasta(uploaded_info)
        elif info_file_type == "csv":
            info_df = read_table(uploaded_info, "csv", delimiter=default_delim, header_row=default_header, encoding=default_encoding)
        elif info_file_type == "excel":
            info_df = read_table(uploaded_info, "xlsx", header_row=default_header)
    except Exception:
        info_df = pd.DataFrame()

st.header("Info file preview")
df_preview(info_df)

# --- Targets preview and parsing options -----------------------------------

st.markdown("---")
st.header("Target files (preview and parsing)")

target_dfs = {}
target_options = {}

for i, f in enumerate(uploaded_targets or []):
    st.subheader(f"Target file: {f.name}")
    col1, col2 = st.columns([2, 1])
    with col2:
        # parsing options per target
        t_delim = st.text_input(f"Delimiter for {f.name}", value=default_delim, key=f"delim_{i}")
        t_header = st.number_input(f"Header row index for {f.name}", value=default_header, key=f"header_{i}", min_value=0)
        t_enc = st.text_input(f"Encoding for {f.name}", value=default_encoding, key=f"encoding_{i}")
    with col1:
        # attempt to parse
        name = f.name.lower()
        if name.endswith((".xls", ".xlsx")):
            df = read_table(f, "xlsx", header_row=t_header, encoding=t_enc)
        else:
            df = read_table(f, "csv", delimiter=t_delim, header_row=t_header, encoding=t_enc)
        target_dfs[f.name] = df
        df_preview(df)

# --- Merge configuration ----------------------------------------------------

st.markdown("---")
st.header("Merge configuration")

if info_df is None or info_df.empty:
    st.warning("Please upload and preview an information file first.")
else:
    st.subheader("Select key column in info file")
    info_key = st.selectbox("Info key column (matching field)", options=["(index)"] + list(info_df.columns), index=1 if len(info_df.columns)>0 else 0)
    st.subheader("Select columns to keep from info file")
    info_keep = st.multiselect("Columns to keep from info file (these will be added to targets)", options=list(info_df.columns), default=list(info_df.columns)[:2])

    # For FASTA, common use-case: accession -> description
    if info_file_type == "fasta":
        # If parse_fasta created 'accession' and 'description'
        if "accession" in info_df.columns:
            info_key = st.selectbox("Info key column (FASTA)", options=list(info_df.columns), index=list(info_df.columns).index("accession"))
            if "description" in info_df.columns and "description" not in info_keep:
                info_keep.insert(0, "description")

    st.markdown("----")
    st.subheader("For each target file: choose matching key and columns to keep")

    merged_results = {}
    for tname, tdf in target_dfs.items():
        st.write(f"**Target:** {tname}")
        if tdf is None or tdf.empty:
            st.write("No data parsed for this target.")
            continue

        t_key = st.selectbox(f"Select key column in {tname}", options=["(index)"] + list(tdf.columns), key=f"tkey_{tname}")
        t_keep = st.multiselect(f"Columns to keep from {tname} (in result)", options=list(tdf.columns), default=list(tdf.columns))
        how = st.selectbox(f"Merge type for {tname}", options=["left", "inner", "right", "outer"], index=0, key=f"how_{tname}")

        # Prepare dataframes for merge
        left_df = tdf.copy()
        right_df = info_df.copy()

        # If user selected "(index)" use index as key
        left_on = None
        right_on = None
        if t_key == "(index)":
            left_df = left_df.reset_index().rename(columns={"index": "index_key"})
            left_on = "index_key"
        else:
            left_on = t_key

        if info_key == "(index)":
            right_df = right_df.reset_index().rename(columns={"index": "index_key"})
            right_on = "index_key"
        else:
            right_on = info_key

        # Subset columns to keep
        left_cols = t_keep.copy()
        if left_on not in left_cols:
            left_cols = [left_on] + left_cols
        right_cols = info_keep.copy()
        if right_on not in right_cols:
            right_cols = [right_on] + right_cols

        # Avoid duplicate column names by suffixing
        try:
            merged = pd.merge(left_df[left_cols], right_df[right_cols], left_on=left_on, right_on=right_on, how=how, suffixes=("", "_info"))
        except Exception as e:
            st.error(f"Merge failed for {tname}: {e}")
            merged = pd.DataFrame()

        st.write("Merged preview:")
        df_preview(merged, n=10)

        # Allow renaming or dropping columns interactively
        if not merged.empty:
            st.markdown(f"**Adjust columns for {tname}**")
            cols_to_drop = st.multiselect(f"Columns to drop from merged {tname}", options=list(merged.columns), key=f"drop_{tname}")
            if cols_to_drop:
                merged = merged.drop(columns=cols_to_drop)
            # Optionally rename columns
            if st.checkbox(f"Rename columns for {tname}", key=f"rename_{tname}"):
                new_names = {}
                for c in merged.columns:
                    new = st.text_input(f"Rename column '{c}'", value=c, key=f"rename_{tname}_{c}")
                    new_names[c] = new
                merged = merged.rename(columns=new_names)

        merged_results[tname] = merged

    # --- Batch apply and download ------------------------------------------
    st.markdown("---")
    st.header("Download merged results")
    for tname, mdf in merged_results.items():
        if mdf is None or mdf.empty:
            st.write(f"No merged result for {tname}")
            continue
        st.write(f"**{tname}**")
        st.markdown(download_link(mdf, filename=f"merged_{tname}.xlsx"), unsafe_allow_html=True)
        # Also allow CSV download
        csv = mdf.to_csv(index=False).encode("utf-8")
        b64 = base64.b64encode(csv).decode()
        href = f'<a href="data:file/csv;base64,{b64}" download="merged_{tname}.csv">Download merged_{tname}.csv</a>'
        st.markdown(href, unsafe_allow_html=True)

st.markdown("---")
st.caption("App built with Streamlit. For large files, consider running locally and increasing memory limits.")
