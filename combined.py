import streamlit as st
import requests
import json
import base64
from datetime import datetime
from mistralai import Mistral
import re

# Set page config
st.set_page_config(
    page_title="Oracle Fusion Invoice Creator with OCR", 
    layout="wide"
)

# Title
st.title("🧾 Oracle Fusion Invoice Creator with PDF OCR")
st.markdown("Upload an invoice PDF, extract data with AI, and create AP invoices in Oracle Fusion")

# Initialize session state
if "ocr_result" not in st.session_state:
    st.session_state["ocr_result"] = None
if "extracted_data" not in st.session_state:
    st.session_state["extracted_data"] = {}
if "pdf_processed" not in st.session_state:
    st.session_state["pdf_processed"] = False

# Sidebar for API configurations
st.sidebar.header("🔧 API Configuration")

# Mistral API Key
mistral_api_key = st.sidebar.text_input("Mistral API Key", type="password")

# Oracle Fusion Configuration
st.sidebar.subheader("Oracle Fusion Settings")
auth_method = st.sidebar.selectbox("Authentication Method", ["Basic Auth", "OAuth2"])

if auth_method == "Basic Auth":
    username = st.sidebar.text_input("Username", type="password")
    password = st.sidebar.text_input("Password", type="password")
else:
    access_token = st.sidebar.text_input("Access Token", type="password")

fusion_url = st.sidebar.text_input(
    "Oracle Fusion Base URL",
    placeholder="https://your-instance.oraclecloud.com"
)

# Step 1: PDF Upload and OCR Processing
st.header("📄 Step 1: Upload Invoice PDF")

uploaded_file = st.file_uploader("Upload Invoice PDF", type=["pdf"])

if uploaded_file and mistral_api_key:
    if st.button("🔍 Extract Invoice Data", type="primary"):
        with st.spinner("Processing PDF with Mistral OCR..."):
            try:
                client = Mistral(api_key=mistral_api_key)
                
                # Read and encode PDF
                file_bytes = uploaded_file.read()
                encoded_pdf = base64.b64encode(file_bytes).decode("utf-8")
                
                document = {
                    "type": "document_url",
                    "document_url": f"data:application/pdf;base64,{encoded_pdf}"
                }
                
                # Process with Mistral OCR
                ocr_response = client.ocr.process(
                    model="mistral-ocr-latest",
                    document=document,
                    include_image_base64=True
                )
                
                # Extract text
                if hasattr(ocr_response, "pages"):
                    pages = ocr_response.pages
                elif isinstance(ocr_response, list):
                    pages = ocr_response
                else:
                    pages = []
                
                result_text = "\n\n".join(page.markdown for page in pages)
                st.session_state["ocr_result"] = result_text
                st.session_state["pdf_processed"] = True
                
                st.success("✅ PDF processed successfully!")
                
            except Exception as e:
                st.error(f"❌ Error processing PDF: {str(e)}")

# Display OCR result and data extraction
if st.session_state["pdf_processed"] and st.session_state["ocr_result"]:
    
    # Show OCR result
    with st.expander("📋 Raw OCR Text", expanded=False):
        st.text_area("Extracted Text", st.session_state["ocr_result"], height=200)
    
    # Step 2: Smart Data Extraction
    st.header("🤖 Step 2: Extract Invoice Fields")
    
    if st.button("🧠 Auto-Extract Invoice Data"):
        with st.spinner("Extracting invoice fields with AI..."):
            try:
                # Use another Mistral call to structure the data
                client = Mistral(api_key=mistral_api_key)
                
                extraction_prompt = f"""
                Analyze this invoice text and extract the following information in JSON format:
                
                {{
                    "invoice_number": "invoice number",
                    "invoice_date": "date in YYYY-MM-DD format",
                    "invoice_amount": "total amount as number",
                    "supplier_name": "vendor/supplier name",
                    "supplier_address": "supplier address",
                    "currency": "currency code (default USD)",
                    "description": "invoice description or main service/product",
                    "line_items": [
                        {{
                            "description": "line item description",
                            "amount": "line amount as number"
                        }}
                    ]
                }}
                
                Invoice Text:
                {st.session_state["ocr_result"]}
                
                Return only the JSON object, no other text.
                """
                
                chat_response = client.chat.complete(
                    model="mistral-large-latest",
                    messages=[{"role": "user", "content": extraction_prompt}]
                )
                
                # Parse the response
                extracted_json = chat_response.choices[0].message.content
                
                # Clean up the response to extract JSON
                json_match = re.search(r'\{.*\}', extracted_json, re.DOTALL)
                if json_match:
                    extracted_data = json.loads(json_match.group())
                    st.session_state["extracted_data"] = extracted_data
                    st.success("✅ Invoice data extracted successfully!")
                else:
                    st.error("❌ Could not parse extracted data")
                    
            except Exception as e:
                st.error(f"❌ Error extracting data: {str(e)}")
    
    # Step 3: Review and Edit Extracted Data
    if st.session_state["extracted_data"]:
        st.header("✏️ Step 3: Review & Edit Invoice Data")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Invoice Header")
            
            # Oracle-specific required fields
            business_unit = st.text_input(
                "Business Unit *", 
                help="Required - Oracle Fusion Business Unit code"
            )
            
            supplier_name = st.text_input(
                "Supplier Name *", 
                value=st.session_state["extracted_data"].get("supplier_name", "")
            )
            
            supplier_site = st.text_input(
                "Supplier Site *", 
                help="Required - Must exist in Oracle Fusion"
            )
            
            invoice_number = st.text_input(
                "Invoice Number *", 
                value=st.session_state["extracted_data"].get("invoice_number", "")
            )
            
            invoice_amount = st.number_input(
                "Invoice Amount *", 
                value=float(st.session_state["extracted_data"].get("invoice_amount", 0)),
                min_value=0.01,
                step=0.01
            )
            
            # Parse date from extracted data
            extracted_date = st.session_state["extracted_data"].get("invoice_date", "")
            try:
                if extracted_date:
                    invoice_date = st.date_input(
                        "Invoice Date *", 
                        value=datetime.strptime(extracted_date, "%Y-%m-%d").date()
                    )
                else:
                    invoice_date = st.date_input("Invoice Date *", value=datetime.now().date())
            except:
                invoice_date = st.date_input("Invoice Date *", value=datetime.now().date())
        
        with col2:
            st.subheader("Additional Details")
            
            invoice_currency = st.text_input(
                "Currency *", 
                value=st.session_state["extracted_data"].get("currency", "USD")
            )
            
            payment_terms = st.text_input("Payment Terms", placeholder="e.g., NET30")
            
            invoice_group = st.text_input("Invoice Group", help="Optional")
            
            description = st.text_area(
                "Description", 
                value=st.session_state["extracted_data"].get("description", "")
            )
        
        # Invoice Lines
        st.subheader("Invoice Lines")
        
        # Auto-populate from extracted data
        extracted_lines = st.session_state["extracted_data"].get("line_items", [])
        if not extracted_lines:
            extracted_lines = [{"description": "Service", "amount": invoice_amount}]
        
        num_lines = st.number_input(
            "Number of Lines", 
            min_value=1, 
            max_value=10, 
            value=len(extracted_lines)
        )
        
        lines_data = []
        for i in range(num_lines):
            st.write(f"**Line {i+1}**")
            col1, col2 = st.columns(2)
            
            with col1:
                line_amount = st.number_input(
                    f"Amount {i+1} *",
                    value=float(extracted_lines[i]["amount"]) if i < len(extracted_lines) else 0.0,
                    min_value=0.01,
                    step=0.01,
                    key=f"amount_{i}"
                )
            
            with col2:
                distribution_comb = st.text_input(
                    f"Distribution Combination {i+1} *",
                    placeholder="e.g., 101.10.52496.120.000.000",
                    key=f"dist_{i}",
                    help="Chart of Accounts combination"
                )
            
            lines_data.append({
                "amount": line_amount,
                "dist_comb": distribution_comb
            })
        
        # Step 4: Create Oracle Invoice
        st.header("🚀 Step 4: Create Oracle Fusion Invoice")
        
        if st.button("📤 Create Invoice in Oracle", type="primary"):
            # Validation
            required_fields = [
                business_unit, supplier_name, supplier_site, 
                invoice_number, fusion_url, invoice_currency
            ]
            
            if auth_method == "Basic Auth":
                required_fields.extend([username, password])
            else:
                required_fields.append(access_token)
            
            if not all(required_fields):
                st.error("❌ Please fill in all required fields marked with *")
            elif invoice_amount <= 0:
                st.error("❌ Invoice amount must be greater than 0")
            elif abs(sum(line["amount"] for line in lines_data) - invoice_amount) > 1e-6:
                st.error("❌ Sum of line amounts must equal invoice amount")
            elif not all(line["dist_comb"] for line in lines_data):
                st.error("❌ All lines must have distribution combinations")
            else:
                try:
                    # Create authentication header
                    if auth_method == "Basic Auth":
                        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
                        auth_header = {"Authorization": f"Basic {credentials}"}
                    else:
                        auth_header = {"Authorization": f"Bearer {access_token}"}
                    
                    # Build payload
                    invoice_lines = []
                    for idx, line in enumerate(lines_data):
                        line_payload = {
                            "LineNumber": idx + 1,
                            "LineAmount": line["amount"],
                            "AccountingDate": invoice_date.strftime("%Y-%m-%d"),
                            "DistributionCombination": line["dist_comb"]
                        }
                        invoice_lines.append(line_payload)
                    
                    payload = {
                        "InvoiceNumber": invoice_number,
                        "InvoiceCurrency": invoice_currency,
                        "InvoiceAmount": invoice_amount,
                        "InvoiceDate": invoice_date.strftime("%Y-%m-%d"),
                        "BusinessUnit": business_unit,
                        "Supplier": supplier_name,
                        "SupplierSite": supplier_site,
                        "InvoiceGroup": invoice_group,
                        "Description": description,
                        "invoiceLines": invoice_lines
                    }
                    
                    # API call
                    api_endpoint = f"{fusion_url.rstrip('/')}/fscmRestApi/resources/11.13.18.05/invoices"
                    headers = {
                        "Content-Type": "application/vnd.oracle.adf.resourceitem+json",
                        "Accept": "application/json",
                        **auth_header
                    }
                    
                    with st.expander("📋 Review API Payload"):
                        st.json(payload)
                    
                    with st.spinner("Creating invoice in Oracle Fusion..."):
                        response = requests.post(
                            api_endpoint, 
                            headers=headers, 
                            json=payload, 
                            timeout=30
                        )
                    
                    if response.status_code in (200, 201):
                        st.success("🎉 Invoice created successfully in Oracle Fusion!")
                        st.json(response.json())
                    else:
                        st.error(f"❌ Error creating invoice: {response.status_code}")
                        st.error(f"Response: {response.text}")
                        
                except requests.exceptions.RequestException as e:
                    st.error(f"❌ Network error: {str(e)}")
                except Exception as e:
                    st.error(f"❌ Unexpected error: {str(e)}")

# Information sections
st.sidebar.markdown("---")
st.sidebar.subheader("ℹ️ Requirements")
st.sidebar.info("""
**Required:**
- Mistral API key for OCR
- Oracle Fusion credentials
- Valid Business Unit
- Existing Supplier & Site
- Chart of Accounts combinations
""")

# Instructions
with st.expander("📖 How to Use This Tool"):
    st.markdown("""
    ### Step-by-Step Instructions:
    
    1. **Configure APIs**: Enter your Mistral API key and Oracle Fusion credentials in the sidebar
    
    2. **Upload PDF**: Upload your supplier invoice PDF file
    
    3. **Extract Data**: Click "Extract Invoice Data" to process the PDF with OCR
    
    4. **Auto-Extract Fields**: Use AI to automatically identify invoice fields
    
    5. **Review & Edit**: Verify and correct the extracted data, especially Oracle-specific fields:
       - Business Unit (must exist in your Oracle instance)
       - Supplier Site (must be active)
       - Distribution Combinations (valid Chart of Accounts)
    
    6. **Create Invoice**: Submit to Oracle Fusion Payables
    
    ### Important Notes:
    - Ensure your Oracle user has Payables Invoice Entry privileges
    - Supplier and supplier site must exist and be active in Oracle
    - Distribution combinations must be valid COA strings
    - Line amounts must sum to invoice total
    """)