# from scraper_setup import get_driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import TimeoutException
import json
import time

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

def get_driver():
    """Create a stable Chrome driver with optimized options"""
    chrome_options = Options()
    
    # Optional: Run headless (no browser window)
    # chrome_options.add_argument("--headless")
    
    # Stability and privacy options
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Disable cache for fresh data
    chrome_options.add_argument("--disable-application-cache")
    chrome_options.add_argument("--disk-cache-size=0")
    
    # Performance and stability settings
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    
    # Suppress logging
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])
    
    # Download settings
    chrome_options.add_experimental_option("prefs", {
        "download.default_directory": "./downloads",
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    })
    
    # Create driver with webdriver-manager (auto-downloads chromedriver)
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )
    
    # Set timeouts
    driver.set_page_load_timeout(30)
    driver.implicitly_wait(10)
    
    return driver

# --- CONFIGURATION ---
GLOBAL_TIMEOUT = 45 

REACTION_ROLE_MAPPING = {
    0: "UNSPECIFIED", 1: "REACTANT", 2: "REAGENT", 3: "SOLVENT",
    4: "CATALYST", 5: "WORKUP", 6: "INTERNAL_STANDARD",
    7: "AUTHENTIC_STANDARD", 8: "PRODUCT", 9: "BYPRODUCT", 10: "SIDE_PRODUCT"
}
IDENTIFIER_TYPE_MAPPING = {
    0: "UNSPECIFIED",
    1: "CUSTOM",
    2: "SMILES",
    3: "INCHI",
    4: "MOLBLOCK",
    5: "FINGERPRINT",
    6: "NAME",          
    7: "IUPAC_NAME",    
    8: "CAS_NUMBER"     
}

# --- FORMATTER FUNCTION (YOUR CODE) ---
def format_reaction_data(reaction_data):
    """Extract all identifiers types, amount, and reaction_role with CORRECT mappings."""
    if not reaction_data or 'data' not in reaction_data:
        return None
    
    data = reaction_data['data']
    formatted = {
        'reaction_id': data.get('reactionId'),
        'success': reaction_data.get('success', True), # specific handle if success missing
        'inputsMap': []
    }

    # --- MAPPINGS BASED ON ORD PROTOBUF DEFINITIONS ---
    # Mass: 1=KG, 2=G, 3=MG, 4=UG
    MASS_UNIT_MAPPING = { 0: "UNSPECIFIED", 1: "KILOGRAM", 2: "GRAM", 3: "MILLIGRAM", 4: "MICROGRAM" }
    
    # Volume: 1=L, 2=ML, 3=UL, 4=NL
    VOLUME_UNIT_MAPPING = { 0: "UNSPECIFIED", 1: "LITER", 2: "MILLILITER", 3: "MICROLITER", 4: "NANOLITER" }
    
    # Moles: 1=MOL, 2=MMOL, 3=UMOL, 4=NMOL
    MOLE_UNIT_MAPPING = { 0: "UNSPECIFIED", 1: "MOLE", 2: "MILLIMOLE", 3: "MICROMOLE", 4: "NANOMOLE" }

    def extract_identifiers(item):
        extracted_ids = []
        for identifier in item.get("identifiersList", []):
            type_int = identifier.get("type", 0)
            type_str = IDENTIFIER_TYPE_MAPPING.get(type_int, "UNKNOWN")
            extracted_ids.append({
                "type": type_str,
                "value": identifier.get("value")
            })
        return extracted_ids
    if 'inputsMap' in data:
        for input_entry in data["inputsMap"]:
            tab_name = input_entry[0]
            input_data = input_entry[1]
            
            formatted_components = []
            for component in input_data.get("componentsList", []):
                
                identifiers = extract_identifiers(component)
                
                amount_data = {}
                if 'amount' in component:
                    amt = component['amount']
                    
                    if 'moles' in amt:
                        val = amt['moles'].get('value')
                        unit_id = amt['moles'].get('units', 0)
                        amount_data = {
                            "moles": { "value": val, "units": MOLE_UNIT_MAPPING.get(unit_id, "UNKNOWN") }
                        }
                    elif 'volume' in amt:
                        val = amt['volume'].get('value')
                        unit_id = amt['volume'].get('units', 0)
                        amount_data = {
                            "volume": { "value": val, "units": VOLUME_UNIT_MAPPING.get(unit_id, "UNKNOWN") }
                        }
                    elif 'mass' in amt:
                        val = amt['mass'].get('value')
                        unit_id = amt['mass'].get('units', 0)
                        amount_data = {
                            "mass": { "value": val, "units": MASS_UNIT_MAPPING.get(unit_id, "UNKNOWN") }
                        }
                
                reaction_role_value = component.get("reactionRole")
                reaction_role = REACTION_ROLE_MAPPING.get(reaction_role_value, "UNKNOWN")
                
                component_info = {
                    "identifiers": identifiers,
                    "amount": amount_data,
                    "reaction_role": reaction_role
                }
                formatted_components.append(component_info)
            
            formatted_input = [ tab_name, { "components": formatted_components } ]
            formatted['inputsMap'].append(formatted_input)
    
    formatted['outcomes'] = []
    if 'outcomesList' in data:
        for outcome in data['outcomesList']:
            for product in outcome.get('productsList', []):
                
                identifiers = extract_identifiers(product)
                
                # --- FIXED MEASUREMENT LOGIC ---
                # We need to map the measurements (Yield/Mass) similar to how we mapped inputs
                formatted_measurements = []
                for meas in product.get('measurementsList', []):
                    # Check if it's a MASS measurement (Type 9 usually, but we check structure)
                    meas_data = {"type": meas.get("type"), "details": meas.get("details")}
                    
                    # Extract amount if present in measurement
                    if 'amount' in meas and 'mass' in meas['amount']:
                         val = meas['amount']['mass'].get('value')
                         unit_id = meas['amount']['mass'].get('units', 0)
                         meas_data['mass'] = {
                             "value": val,
                             "units": MASS_UNIT_MAPPING.get(unit_id, "UNKNOWN")
                         }
                    formatted_measurements.append(meas_data)

                product_info = {
                    "identifiers": identifiers,
                    "reaction_role": "PRODUCT",
                    "is_desired_product": product.get('isDesiredProduct', False),
                    "measurements": formatted_measurements
                }
                formatted['outcomes'].append(product_info)
    
    return formatted

# --- CORE SCRAPING FUNCTIONS ---

def wait_for_page_load(driver, timeout=GLOBAL_TIMEOUT):
    """Robust wait for page to be fully loaded"""
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(1) 
    except TimeoutException:
        print("  Warning: Page load timed out, but continuing...")

def get_all_dataset_ids(start_index=None, end_index=None):
    """Get dataset IDs with optimization to stop early"""
    driver = get_driver()
    try:
        driver.get("https://open-reaction-database.org/browse")
        wait_for_page_load(driver)
        wait = WebDriverWait(driver, GLOBAL_TIMEOUT)
        
        try:
            print(f"Selecting 100 datasets per page...")
            select_element = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "select#pagination"))
            )
            select = Select(select_element)
            select.select_by_value('100')
            print(f"Waiting for table to refresh...")
            time.sleep(5) 
        except Exception as e:
            print(f"Warning: Could not select 100 entries: {e}")
        
        # Calculate Total Pages
        total_pages = None
        try:
            pagination_div = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "div.pagination div.select")))
            pagination_text = pagination_div.text
            import re
            match = re.search(r'of (\d+) entries', pagination_text)
            if match:
                total_entries = int(match.group(1))
                if end_index is not None and end_index > total_entries:
                    end_index = total_entries
                entries_per_page = 100
                total_pages = (total_entries + entries_per_page - 1) // entries_per_page
                print(f"Total entries available: {total_entries}")
        except Exception as e:
            print(f"Warning: Could not determine total pages: {e}")
        
        all_dataset_ids = []
        page_num = 1
        stop_scraping = False 
        
        while True:
            print(f"Scraping page {page_num}...")
            try:
                dataset_links = wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[href*='/dataset/ord_dataset-']"))
                )
                
                print(f"  Found {len(dataset_links)} dataset links on page {page_num}")
                
                for link in dataset_links:
                    href = link.get_attribute('href')
                    dataset_id = href.split('/')[-1]
                    if dataset_id not in all_dataset_ids:
                        all_dataset_ids.append(dataset_id)
                        if end_index is not None and len(all_dataset_ids) >= end_index:
                            stop_scraping = True
                            break
            except Exception as e:
                print(f"  Error finding dataset links: {e}")
                break
            
            if stop_scraping: break
            if total_pages and page_num >= total_pages: break
            
            try:
                next_button = driver.find_element(By.CSS_SELECTOR, "div.next.paginav")
                if "no-click" in next_button.get_attribute("class"): break
                driver.execute_script("arguments[0].click();", next_button)
                time.sleep(5) 
                page_num += 1
            except:
                break
        
        start = (start_index - 1) if start_index is not None else 0
        if start < 0: start = 0
        filtered_dataset_ids = all_dataset_ids[start:]
        return filtered_dataset_ids
        
    finally:
        driver.quit()

def get_user_input():
    print("\n" + "="*60)
    print("REACTION DATABASE SCRAPER - CONFIGURATION")
    print("="*60)
    print("1. Scrape ALL datasets")
    print("2. Scrape SPECIFIC datasets by ID")
    print("3. Scrape UNIFORM range")
    print("4. Scrape CUSTOM ranges")
    print("5. Scrape SINGLE specific reaction (Target Mode)") 
    
    mode = input("\nEnter mode (1-5): ").strip()
    
    if mode == "1":
        d_start = input("Start dataset index (1-based, Enter for 1): ").strip()
        d_end = input("End dataset index (1-based, Enter for All): ").strip()
        d_s = int(d_start) if d_start else None
        d_e = int(d_end) if d_end else None
        return {'mode': 'all', 'max_workers': 3, 'dataset_start': d_s, 'dataset_end': d_e}
    elif mode == "2":
        ids = input("Enter dataset IDs (comma-separated): ").strip().split(',')
        return {'mode': 'specific_datasets', 'dataset_ids': [d.strip() for d in ids if d.strip()], 'max_workers': 3}
    elif mode == "3":
        d_s = input("Start dataset index: ").strip()
        d_e = input("End dataset index: ").strip()
        r_s = input("Start reaction index: ").strip()
        r_e = input("End reaction index: ").strip()
        return {'mode': 'uniform_range', 'dataset_start': int(d_s) if d_s else None, 'dataset_end': int(d_e) if d_e else None, 
                'reaction_start': int(r_s) if r_s else None, 'reaction_end': int(r_e) if r_e else None, 'max_workers': 3}
    elif mode == "4":
        ranges = {}
        while True:
            did = input("Enter dataset ID (Enter to finish): ").strip()
            if not did: break
            s = input(f"  Start idx for {did}: ").strip()
            e = input(f"  End idx for {did}: ").strip()
            ranges[did] = (int(s) if s else None, int(e) if e else None)
        return {'mode': 'custom_ranges', 'dataset_ranges': ranges, 'max_workers': 3}
    elif mode == "5":
        d = input("Enter Dataset Index (e.g., 50): ").strip()
        if not d: return get_user_input()
        r = input("Enter Reaction Index (e.g., 1): ").strip() or "1"
        return {'mode': 'single_target', 'dataset_target': int(d), 'reaction_target': int(r), 'max_workers': 1}
    else:
        return {'mode': 'all', 'max_workers': 3, 'dataset_start': None, 'dataset_end': None}

def scrape_reaction_data(driver, reaction_id, max_retries=3):
    """Scrape the JSON data from a single reaction page"""
    for attempt in range(max_retries):
        try:
            print(f"  Loading {reaction_id}...")
            driver.get(f"https://open-reaction-database.org/id/{reaction_id}")
            wait_for_page_load(driver)
            wait = WebDriverWait(driver, GLOBAL_TIMEOUT)
            
            # Click Button
            button_xpath = "//div[contains(text(), 'View Full Record')]"
            try:
                button = wait.until(EC.element_to_be_clickable((By.XPATH, button_xpath)))
                driver.execute_script("arguments[0].scrollIntoView(true);", button)
                time.sleep(1) 
                driver.execute_script("arguments[0].click();", button)
            except TimeoutException:
                print(f"    Timeout waiting for button on {reaction_id}")
                raise

            # Get JSON
            print("    Waiting for JSON data...")
            json_xpath = "//div[contains(@class, 'data')]//pre | //pre"
            data_element = wait.until(EC.visibility_of_element_located((By.XPATH, json_xpath)))
            
            json_text = data_element.text
            if not json_text or not json_text.strip().startswith('{'):
                time.sleep(2)
                json_text = data_element.text
                
            if not json_text.strip().startswith('{'):
                raise Exception("Data element found but does not contain JSON")

            reaction_data = json.loads(json_text)
            
            # Close modal
            try:
                close_btn = driver.find_element(By.CSS_SELECTOR, ".close")
                driver.execute_script("arguments[0].click();", close_btn)
            except: pass

            print(f"✓ Scraped raw data: {reaction_id}")
            return {'reaction_id': reaction_id, 'data': reaction_data, 'success': True}
            
        except Exception as e:
            print(f"⚠ Error scraping {reaction_id} (attempt {attempt+1}): {str(e)[:100]}")
            time.sleep(5)
            continue
    
    return {'reaction_id': reaction_id, 'data': None, 'success': False, 'error': 'Max retries exceeded'}

def get_all_reaction_ids_from_dataset(driver, dataset_id, start_index=None, end_index=None):
    try:
        driver.get(f"https://open-reaction-database.org/dataset/{dataset_id}")
        wait_for_page_load(driver)
        wait = WebDriverWait(driver, GLOBAL_TIMEOUT)
        
        try:
            target_value = '100'
            if end_index is not None:
                if end_index <= 10: target_value = '10'
                elif end_index <= 25: target_value = '25'
                elif end_index <= 50: target_value = '50'

            if target_value != '10':
                print(f"  Switching to {target_value} entries...")
                select_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "select#pagination")))
                from selenium.webdriver.support.ui import Select
                select = Select(select_element)
                if select.first_selected_option.get_attribute("value") != target_value:
                    select.select_by_value(target_value)
                    time.sleep(5) 
        except Exception as e:
            print(f"  Pagination warning: {e}")

        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(@href, '/id/ord-')]")))
        except TimeoutException:
            return []

        links = driver.find_elements(By.XPATH, "//a[contains(@href, '/id/ord-')]")
        all_reaction_ids = []
        for link in links:
            href = link.get_attribute('href')
            if href:
                rid = href.split('/')[-1]
                if rid.startswith('ord-') and rid not in all_reaction_ids:
                    all_reaction_ids.append(rid)
        
        start = (start_index - 1) if start_index is not None else 0
        end = end_index if end_index is not None else len(all_reaction_ids)
        if start < 0: start = 0
        if end > len(all_reaction_ids): end = len(all_reaction_ids)
        
        return all_reaction_ids[start:end]
    except Exception as e:
        print(f"Error getting reactions from {dataset_id}: {e}")
        return []

def scrape_single_dataset(dataset_id, start_index=None, end_index=None):
    driver = get_driver()
    try:
        print(f"\n{'='*60}\nProcessing dataset: {dataset_id}\n{'='*60}")
        reaction_ids = get_all_reaction_ids_from_dataset(driver, dataset_id, start_index, end_index)
        
        if not reaction_ids:
            return {'dataset_id': dataset_id, 'reactions': [], 'total_reactions': 0, 'successful_scrapes': 0}
        
        reactions_data = []
        for i, reaction_id in enumerate(reaction_ids, 1):
            print(f"  [{i}/{len(reaction_ids)}] Scraping {reaction_id}...")
            result = scrape_reaction_data(driver, reaction_id)
            
            # --- APPLY FORMATTING HERE ---
            if result['success']:
                try:
                    formatted = format_reaction_data(result)
                    result['formatted_data'] = formatted
                    print(f"    ✓ Formatted {reaction_id}")
                except Exception as e:
                    print(f"    ⚠ Error formatting {reaction_id}: {e}")
            
            reactions_data.append(result)
            time.sleep(1) 
        
        successful = sum(1 for r in reactions_data if r['success'])
        return {'dataset_id': dataset_id, 'reactions': reactions_data, 'total_reactions': len(reactions_data), 'successful_scrapes': successful}
        
    except Exception as e:
        print(f"✗ Error with dataset {dataset_id}: {e}")
        return {'dataset_id': dataset_id, 'reactions': [], 'total_reactions': 0, 'successful_scrapes': 0, 'error': str(e)}
    finally:
        driver.quit()

def scrape_all_datasets_parallel(max_workers=3, dataset_ranges=None, specific_datasets=None, 
                                 dataset_start=None, dataset_end=None, 
                                 reaction_start=None, reaction_end=None):
    print("="*60 + "\nSTARTING WEB SCRAPING (PARALLEL)\n" + "="*60)
    
    if specific_datasets:
        dataset_ids = specific_datasets
    else:
        dataset_ids = get_all_dataset_ids(dataset_start, dataset_end)
    
    if not dataset_ids:
        print("✗ No valid datasets to scrape!")
        return []
    
    all_results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_dataset = {}
        for dataset_id in dataset_ids:
            if dataset_ranges and dataset_id in dataset_ranges:
                start, end = dataset_ranges[dataset_id]
                future = executor.submit(scrape_single_dataset, dataset_id, start, end)
            elif reaction_start is not None or reaction_end is not None:
                future = executor.submit(scrape_single_dataset, dataset_id, reaction_start, reaction_end)
            else:
                future = executor.submit(scrape_single_dataset, dataset_id)
            future_to_dataset[future] = dataset_id
        
        for i, future in enumerate(as_completed(future_to_dataset), 1):
            dataset_id = future_to_dataset[future]
            try:
                result = future.result()
                all_results.append(result)
                print(f"✓ Completed dataset {i}/{len(dataset_ids)}: {dataset_id}")
            except Exception as e:
                print(f"✗ Failed dataset {dataset_id}: {e}")
                all_results.append({'dataset_id': dataset_id, 'error': str(e)})
    
    return all_results

def main():
    print(f"\n{'='*60}")
    print(f"                      ORD SCRAPER ")
    print(f"Developed by: LAROCO, Jan Lorenz & BARRAL, Jacinth Cedric")
    print(f"{'='*60}")
    config = get_user_input()
    print(f"\nMode: {config['mode']}\n")
    
    results = []
    if config['mode'] == 'all':
        results = scrape_all_datasets_parallel(max_workers=config['max_workers'], dataset_start=config.get('dataset_start'), dataset_end=config.get('dataset_end'))
    elif config['mode'] == 'specific_datasets':
        results = scrape_all_datasets_parallel(max_workers=config['max_workers'], specific_datasets=config['dataset_ids'])
    elif config['mode'] == 'uniform_range':
        results = scrape_all_datasets_parallel(max_workers=config['max_workers'], dataset_start=config.get('dataset_start'), dataset_end=config.get('dataset_end'), reaction_start=config.get('reaction_start'), reaction_end=config.get('reaction_end'))
    elif config['mode'] == 'custom_ranges':
        results = scrape_all_datasets_parallel(max_workers=config['max_workers'], dataset_ranges=config['dataset_ranges'])
    elif config['mode'] == 'single_target':
        results = scrape_all_datasets_parallel(max_workers=1, dataset_start=config['dataset_target'], dataset_end=config['dataset_target'], reaction_start=config['reaction_target'], reaction_end=config['reaction_target'])

    # --- SAVE ONLY FORMATTED DATA ---
    formatted_output = {}
    
    for dataset in results:
        d_id = dataset.get('dataset_id')
        if d_id:
            formatted_output[d_id] = {
                'dataset_id': d_id,
                'total_reactions_scraped': dataset.get('total_reactions', 0),
                'reactions': []
            }
            # Only save the 'formatted_data' part
            for reaction in dataset.get('reactions', []):
                if reaction.get('success') and 'formatted_data' in reaction:
                    formatted_output[d_id]['reactions'].append(reaction['formatted_data'])

    output_file = 'ord_formatted_data.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(formatted_output, f, indent=2, ensure_ascii=False)
    print(f"\n✓ Saved formatted results to {output_file}")

if __name__ == "__main__":
    main()