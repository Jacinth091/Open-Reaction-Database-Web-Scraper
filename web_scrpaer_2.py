from scraper_setup import get_driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium.webdriver.support.ui import Select
import json
import time
REACTION_ROLE_MAPPING = {
    0: "UNSPECIFIED",
    1: "REACTANT",
    2: "REAGENT", 
    3: "SOLVENT",
    4: "CATALYST",
    5: "WORKUP",
    6: "INTERNAL_STANDARD",
    7: "AUTHENTIC_STANDARD",
    8: "PRODUCT",
    9: "BYPRODUCT",
    10: "SIDE_PRODUCT"
}
def get_all_dataset_ids(start_index=None, end_index=None):
    """Get dataset IDs with optimization to stop early if range is satisfied"""
    driver = get_driver()
    try:
        driver.get("https://open-reaction-database.org/browse")
        wait = WebDriverWait(driver, 15)
        
        # Wait for page to load
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)
        
        # SELECT THE 100 OPTION FROM THE DROPDOWN
        try:
            print(f"Selecting 100 datasets per page...")
            select_element = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "select#pagination"))
            )
            select = Select(select_element)
            select.select_by_value('100')
            print(f"Selected 100 entries, waiting for page to refresh...")
            time.sleep(3)
        except Exception as e:
            print(f"Warning: Could not select 100 entries: {e}")
            print(f"Continuing with default pagination...")
        
        # CALCULATE TOTAL PAGES (For logging mainly)
        total_pages = None
        try:
            pagination_div = driver.find_element(By.CSS_SELECTOR, "div.pagination div.select")
            pagination_text = pagination_div.text
            import re
            match = re.search(r'of (\d+) entries', pagination_text)
            if match:
                total_entries = int(match.group(1))
                # Validate end_index against actual total
                if end_index is not None and end_index > total_entries:
                    print(f"Note: Requested end index {end_index} exceeds total entries {total_entries}. Adjusting to max.")
                    end_index = total_entries
                
                entries_per_page = 100
                total_pages = (total_entries + entries_per_page - 1) // entries_per_page
                print(f"Total entries available: {total_entries}")
            else:
                print(f"Could not parse total entries. Will scrape until end or limit reached.")
        except Exception as e:
            print(f"Warning: Could not determine total pages: {e}")
        
        # Now scrape pages
        all_dataset_ids = []
        page_num = 1
        stop_scraping = False # Flag to break the outer loop
        
        while True:
            print(f"Scraping page {page_num}...")
            
            # Find dataset links on current page
            try:
                dataset_links = wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[href*='/dataset/ord_dataset-']"))
                )
                
                print(f"  Found {len(dataset_links)} dataset links on page {page_num}")
                
                # Extract dataset IDs from current page
                for link in dataset_links:
                    href = link.get_attribute('href')
                    dataset_id = href.split('/')[-1]
                    if dataset_id not in all_dataset_ids:
                        all_dataset_ids.append(dataset_id)
                        
                        # --- OPTIMIZATION CHECK ---
                        # If we have reached the user's requested end_index, STOP immediately.
                        if end_index is not None and len(all_dataset_ids) >= end_index:
                            print(f"  ✓ Reached requested limit of {end_index} datasets.")
                            stop_scraping = True
                            break
                            
            except Exception as e:
                print(f"  Error finding dataset links on page {page_num}: {e}")
                break
            
            # Check if we need to stop based on the optimization flag
            if stop_scraping:
                break
            
            # Logic to handle "Next" button
            # Only click next if we haven't reached the calculated total pages (if known)
            if total_pages and page_num >= total_pages:
                print(f"  Completed all available pages.")
                break
            
            try:
                next_button = driver.find_element(By.CSS_SELECTOR, "div.next.paginav")
                if "no-click" in next_button.get_attribute("class"):
                    print(f"  'Next' button disabled - reached last page")
                    break
                
                # Click next
                driver.execute_script("arguments[0].click();", next_button)
                time.sleep(3)
                page_num += 1
                
            except Exception as e:
                print(f"  No 'Next' button found or end of list")
                break
        
        print(f"\nTotal datasets collected: {len(all_dataset_ids)}")
        
        # Slice the final array
        start = (start_index - 1) if start_index is not None else 0
        
        # Ensure start is valid
        if start < 0: start = 0
        
        # Since we stopped scraping exactly at end_index (or earlier), 
        # we can just slice from start to end.
        filtered_dataset_ids = all_dataset_ids[start:]
        
        print(f"Returning datasets {start+1} to {start + len(filtered_dataset_ids)}")
        return filtered_dataset_ids
        
    finally:
        driver.quit()
def get_user_input():
    """Get scraping configuration from user via terminal"""
    print("\n" + "="*60)
    print("REACTION DATABASE SCRAPER - CONFIGURATION")
    print("="*60)
    
    print("\nSelect Scraping Mode:")
    print("1. Scrape ALL datasets (Warning: Very large)")
    print("2. Scrape SPECIFIC datasets by ID (e.g., ord_dataset-...)")
    print("3. Scrape UNIFORM range of reactions from multiple datasets")
    print("4. Scrape CUSTOM ranges for specific datasets")
    print("5. Scrape SINGLE specific reaction from SINGLE dataset index") 
    
    mode = input("\nEnter mode (1-5): ").strip()
    
    # Defaults
    dataset_start = None
    dataset_end = None
    
    if mode == "1":
        # Scrape everything (existing logic)
        print("\nDATASET RANGE:")
        print("Leave blank to scrape ALL 546 datasets")
        d_start = input("Start dataset index (1-based): ").strip()
        d_end = input("End dataset index (1-based): ").strip()
        
        dataset_start = int(d_start) if d_start else None
        dataset_end = int(d_end) if d_end else None
        
        max_workers = int(input("Enter number of parallel workers (recommended: 3): ").strip() or "3")
        return {
            'mode': 'all',
            'max_workers': max_workers,
            'dataset_start': dataset_start,
            'dataset_end': dataset_end
        }
    
    elif mode == "2":
        # Specific Dataset IDs (existing logic)
        print("\n✓ Will scrape specific dataset IDs")
        dataset_ids = input("Enter dataset IDs (comma-separated): ").strip().split(',')
        dataset_ids = [d.strip() for d in dataset_ids if d.strip()]
        max_workers = int(input("Enter workers (def: 3): ").strip() or "3")
        
        return {
            'mode': 'specific_datasets',
            'dataset_ids': dataset_ids,
            'max_workers': max_workers
        }
    
    elif mode == "3":
        # Uniform Range (existing logic)
        print("\n✓ Will scrape same RANGE from selected datasets")
        
        # Select Datasets
        d_start = input("Start dataset index (e.g., 1): ").strip()
        d_end = input("End dataset index (e.g., 50): ").strip()
        dataset_start = int(d_start) if d_start else None
        dataset_end = int(d_end) if d_end else None
        
        # Select Reactions
        r_start = input("Start reaction index (e.g., 1): ").strip()
        r_end = input("End reaction index (e.g., 10): ").strip()
        start_idx = int(r_start) if r_start else None
        end_idx = int(r_end) if r_end else None
        
        max_workers = int(input("Enter workers (def: 3): ").strip() or "3")
        
        return {
            'mode': 'uniform_range',
            'dataset_start': dataset_start,
            'dataset_end': dataset_end,
            'reaction_start': start_idx,
            'reaction_end': end_idx,
            'max_workers': max_workers
        }
    
    elif mode == "4":
        # Custom Ranges (existing logic)
        print("\n✓ Will scrape CUSTOM RANGES")
        dataset_ranges = {}
        while True:
            dataset_id = input("\nEnter dataset ID (Enter to finish): ").strip()
            if not dataset_id: break
            start = input(f"  Start reaction index for {dataset_id}: ").strip()
            end = input(f"  End reaction index for {dataset_id}: ").strip()
            dataset_ranges[dataset_id] = (int(start) if start else None, int(end) if end else None)
        
        max_workers = int(input("Enter workers (def: 3): ").strip() or "3")
        return {
            'mode': 'custom_ranges',
            'dataset_ranges': dataset_ranges,
            'max_workers': max_workers
        }

    # --- NEW MODE 5 ---
    elif mode == "5":
        print("\n✓ SINGLE TARGET MODE")
        print("Select exactly one dataset (1-546) and one reaction index.")
        
        d_idx = input("Enter Dataset Index (e.g., 100): ").strip()
        if not d_idx:
            print("Error: Dataset index required.")
            return get_user_input() # Restart
            
        r_idx = input("Enter Reaction Index (e.g., 1): ").strip()
        if not r_idx: 
            r_idx = "1"
            print("Defaulting to reaction #1")

        d_val = int(d_idx)
        r_val = int(r_idx)
        
        print(f"Target locked: Dataset #{d_val}, Reaction #{r_val}")
        
        return {
            'mode': 'single_target',
            'dataset_target': d_val,
            'reaction_target': r_val,
            'max_workers': 1 # No need for parallel workers for a single item
        }
    
    else:
        print("Invalid mode. Defaulting to mode 1.")
        return {'mode': 'all', 'max_workers': 3, 'dataset_start': None, 'dataset_end': None}
def scrape_reaction_data(driver, reaction_id, max_retries=3):
    """Scrape the JSON data from a single reaction page with retries"""
    for attempt in range(max_retries):
        try:
            print(f"  Loading {reaction_id}...")
            driver.get(f"https://open-reaction-database.org/id/{reaction_id}")
            # Wait for page to be interactive
            WebDriverWait(driver, 15).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            # Wait a bit more for content to load
            time.sleep(2)
            # STEP 1: Find and click the "View Full Record" button
            print(f"    Looking for 'View Full Record' button...")
            # Try multiple selectors for the button
            button_selectors = [
                "div.full-record.button",
                ".full-record.button",
                "//div[contains(@class, 'full-record') and contains(text(), 'View Full Record')]",
                "//div[contains(text(), 'View Full Record')]",
            ]
            button = None
            for selector in button_selectors:
                try:
                    if selector.startswith('//'):
                        button = WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                    else:
                        button = WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                    
                    if button:
                        print(f"    Found button using: {selector}")
                        break
                except:
                    continue
            
            if not button:
                raise Exception("Could not find 'View Full Record' button")
            # Click the button to open the modal
            print("    Clicking 'View Full Record' button...")
            driver.execute_script("arguments[0].click();", button)
            time.sleep(2)  # Wait for modal to open
            # STEP 2: Wait for the modal to appear and find the JSON data
            print("    Looking for JSON data in modal...")
            # Wait for modal to be visible
            modal_selectors = [
                "div.modal-container",
                ".modal-container",
                "//div[contains(@class, 'modal-container')]",
            ]
            modal = None
            for selector in modal_selectors:
                try:
                    if selector.startswith('//'):
                        modal = WebDriverWait(driver, 8).until(
                            EC.visibility_of_element_located((By.XPATH, selector))
                        )
                    else:
                        modal = WebDriverWait(driver, 8).until(
                            EC.visibility_of_element_located((By.CSS_SELECTOR, selector))
                        )
                    
                    if modal:
                        print(f"    Modal found using: {selector}")
                        break
                except:
                    continue
            
            if not modal:
                raise Exception("Modal did not appear after clicking button")
            # STEP 3: Find the JSON data inside the modal
            json_selectors = [
                "div.data pre",
                ".data pre",
                "pre",
                "//pre[contains(text(), 'reactionId')]",
            ]
            data_element = None
            for selector in json_selectors:
                try:
                    if selector.startswith('//'):
                        data_element = WebDriverWait(driver, 8).until(
                            EC.presence_of_element_located((By.XPATH, selector))
                        )
                    else:
                        data_element = WebDriverWait(driver, 8).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                    
                    if data_element:
                        print(f"    Found JSON data using: {selector}")
                        break
                except:
                    continue
            
            if not data_element:
                raise Exception("No JSON element found in modal")
            # Get the text and validate
            json_text = data_element.text
            if not json_text or json_text.strip() == "":
                raise Exception("Empty JSON data")
            if not json_text.strip().startswith('{'):
                raise Exception("Data doesn't look like JSON")
            reaction_data = json.loads(json_text)
            if reaction_data.get('reactionId') != reaction_id:
                raise Exception(f"Reaction ID mismatch: expected {reaction_id}, got {reaction_data.get('reactionId')}")
            try:
                close_button = driver.find_element(By.CSS_SELECTOR, "div.close, .close, [class*='close']")
                driver.execute_script("arguments[0].click();", close_button)
                time.sleep(0.5)
            except:
                pass
            print(f"✓ Successfully scraped: {reaction_id}")
            return {
                'reaction_id': reaction_id,
                'data': reaction_data,
                'success': True
            }
            
        except json.JSONDecodeError as e:
            print(f"⚠ JSON parse error for {reaction_id} (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
                
        except Exception as e:
            print(f"⚠ Error scraping {reaction_id} (attempt {attempt+1}/{max_retries}): {str(e)[:100]}")
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
    
    # All retries failed
    print(f"✗ Failed to scrape {reaction_id} after {max_retries} attempts")
    return {
        'reaction_id': reaction_id,
        'data': None,
        'success': False,
        'error': 'Max retries exceeded'
    }


def get_all_reaction_ids_from_dataset(driver, dataset_id, start_index=None, end_index=None):
    """
    Get reaction IDs from a dataset page with SMART pagination.
    It selects the smallest view (10, 25, 50, 100) necessary to cover the end_index.
    """
    try:
        driver.get(f"https://open-reaction-database.org/dataset/{dataset_id}")
        wait = WebDriverWait(driver, 15)
        
        # Wait for page to load completely
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # --- SMART DROPDOWN SELECTION ---
        try:
            # Determine the best page size based on user input
            target_value = '100' # Default to max if no end_index provided
            
            if end_index is not None:
                if end_index <= 10:
                    target_value = '10'
                elif end_index <= 25:
                    target_value = '25'
                elif end_index <= 50:
                    target_value = '50'
                else:
                    target_value = '100'

            # If target is 10, we can often skip interaction as it's the default
            # But we check just to be safe, or simply skip if we want speed
            if target_value == '10':
                print(f"  Range ({end_index}) fits in default view. Skipping dropdown change.")
                # We still wait a moment for the default table to settle
                time.sleep(1.5)
            else:
                print(f"  Selecting {target_value} entries to cover range up to {end_index}...")
                
                # Find the select element
                select_element = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "select#pagination"))
                )
                
                from selenium.webdriver.support.ui import Select
                select = Select(select_element)
                
                # Check if the option is already selected
                if select.first_selected_option.get_attribute("value") != target_value:
                    select.select_by_value(target_value)
                    print(f"  Waiting for page to refresh with {target_value} entries...")
                    time.sleep(3)  # Necessary wait for table reload
                else:
                    print(f"  Page already showing {target_value} entries.")

        except Exception as e:
            print(f"  Warning: Could not adjust pagination: {e}")
            print(f"  Continuing with current view...")
        
        # --- COLLECT LINKS ---
        # Find reaction links
        selectors = [
            "a[href*='/id/ord-']",
            "//a[contains(@href, '/id/ord-')]",
        ]
        
        reaction_links = []
        for selector in selectors:
            try:
                if selector.startswith('//'):
                    links = driver.find_elements(By.XPATH, selector)
                else:
                    links = driver.find_elements(By.CSS_SELECTOR, selector)
                
                if links:
                    reaction_links = links
                    # Double check: if we found fewer links than requested, warn user
                    if end_index and len(links) < end_index:
                        print(f"  Note: Found {len(links)} links, but requested up to {end_index}.")
                    break
            except:
                continue
        
        # Extract reaction IDs
        all_reaction_ids = []
        for link in reaction_links:
            href = link.get_attribute('href')
            if href:
                reaction_id = href.split('/')[-1]
                if reaction_id.startswith('ord-') and reaction_id not in all_reaction_ids:
                    all_reaction_ids.append(reaction_id)
        
        # --- FILTERING ---
        if start_index is not None or end_index is not None:
            # Convert to 0-based indexing for Python slicing
            start = (start_index - 1) if start_index is not None else 0
            end = end_index if end_index is not None else len(all_reaction_ids)
            
            # Validate indices
            if start < 0: start = 0
            if end > len(all_reaction_ids): end = len(all_reaction_ids)
            
            reaction_ids = all_reaction_ids[start:end]
            print(f"  Filtered to reactions {start+1}-{end} (found {len(all_reaction_ids)} total on page)")
        else:
            reaction_ids = all_reaction_ids
        
        return reaction_ids
        
    except Exception as e:
        print(f"Error getting reactions from {dataset_id}: {e}")
        return []
def scrape_single_dataset(dataset_id, start_index=None, end_index=None):
    """Scrape reactions from a single dataset with optional range
    
    Args:
        dataset_id: The dataset ID to scrape
        start_index: Starting reaction index (1-based, inclusive)
        end_index: Ending reaction index (1-based, inclusive)
    """
    driver = get_driver()
    try:
        print(f"\n{'='*60}")
        print(f"Processing dataset: {dataset_id}")
        if start_index or end_index:
            range_str = f"[{start_index or 'start'} to {end_index or 'end'}]"
            print(f"Range: {range_str}")
        print(f"{'='*60}")
        
        # Step 1: Get reaction IDs in the specified range
        reaction_ids = get_all_reaction_ids_from_dataset(driver, dataset_id, start_index, end_index)
        
        if not reaction_ids:
            print(f"No reactions found in dataset {dataset_id}")
            return {
                'dataset_id': dataset_id,
                'reactions': [],
                'total_reactions': 0,
                'successful_scrapes': 0,
                'error': 'No reactions found'
            }
        
        # Step 2: Scrape each reaction
        reactions_data = []
        for i, reaction_id in enumerate(reaction_ids, 1):
            print(f"  [{i}/{len(reaction_ids)}] Scraping {reaction_id}...")
            result = scrape_reaction_data(driver, reaction_id)
            
            # Format the reaction data
            if result['success']:
                formatted_data = format_reaction_data(result)
                result['formatted_data'] = formatted_data
            
            reactions_data.append(result)
            time.sleep(1)  # Be polite to the server
        
        successful = sum(1 for r in reactions_data if r['success'])
        print(f"\n✓ Dataset {dataset_id} complete: {successful}/{len(reactions_data)} reactions scraped")
        
        return {
            'dataset_id': dataset_id,
            'reactions': reactions_data,
            'total_reactions': len(reactions_data),
            'successful_scrapes': successful
        }
        
    except Exception as e:
        print(f"✗ Error with dataset {dataset_id}: {e}")
        return {
            'dataset_id': dataset_id,
            'reactions': [],
            'total_reactions': 0,
            'successful_scrapes': 0,
            'error': str(e)
        }
    finally:
        driver.quit()

def scrape_all_datasets_parallel(max_workers=3, dataset_ranges=None, specific_datasets=None, 
                                 dataset_start=None, dataset_end=None, 
                                 reaction_start=None, reaction_end=None):
    """Scrape datasets in parallel with comprehensive range options
    
    Args:
        max_workers: Number of parallel workers
        dataset_ranges: Dict mapping dataset_id to (start_index, end_index) tuple for reactions
        specific_datasets: List of specific dataset IDs to scrape
        dataset_start: Starting dataset index (1-based)
        dataset_end: Ending dataset index (1-based)
        reaction_start: Starting reaction index to apply uniformly to all datasets
        reaction_end: Ending reaction index to apply uniformly to all datasets
    """
    
    print("="*60)
    print("STARTING WEB SCRAPING (PARALLEL)")
    print("="*60)
    
    # Step 1: Get dataset IDs with range if specified
    print("\nStep 1: Getting dataset IDs...")
    if specific_datasets:
        # Use specific dataset IDs provided by user
        dataset_ids = specific_datasets
        print(f"Using {len(dataset_ids)} user-specified datasets\n")
    else:
        # Get all datasets with optional range filtering
        all_dataset_ids = get_all_dataset_ids(dataset_start, dataset_end)
        dataset_ids = all_dataset_ids
        print(f"Will scrape {len(dataset_ids)} datasets\n")
    
    if not dataset_ids:
        print("✗ No valid datasets to scrape!")
        return []
    
    # Step 2: Scrape datasets in parallel
    print(f"Step 2: Scraping datasets in parallel (max_workers={max_workers})...\n")
    all_results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_dataset = {}
        for dataset_id in dataset_ids:
            # Determine reaction range for this dataset
            if dataset_ranges and dataset_id in dataset_ranges:
                # Custom range for this specific dataset
                start, end = dataset_ranges[dataset_id]
                future = executor.submit(scrape_single_dataset, dataset_id, start, end)
            elif reaction_start is not None or reaction_end is not None:
                # Uniform range applied to all datasets
                future = executor.submit(scrape_single_dataset, dataset_id, reaction_start, reaction_end)
            else:
                # No range specified, scrape all reactions
                future = executor.submit(scrape_single_dataset, dataset_id)
            
            future_to_dataset[future] = dataset_id
        
        # Process completed tasks
        for i, future in enumerate(as_completed(future_to_dataset), 1):
            dataset_id = future_to_dataset[future]
            try:
                result = future.result()
                all_results.append(result)
                print(f"✓ Completed dataset {i}/{len(dataset_ids)}: {dataset_id}")
            except Exception as e:
                print(f"✗ Failed dataset {dataset_id}: {e}")
                all_results.append({
                    'dataset_id': dataset_id,
                    'error': str(e)
                })
    
    # Step 3: Summary
    total_reactions = sum(r.get('total_reactions', 0) for r in all_results)
    total_successful = sum(r.get('successful_scrapes', 0) for r in all_results)
    
    print(f"\n{'='*60}")
    print(f"SCRAPING COMPLETE!")
    print(f"{'='*60}")
    print(f"Datasets processed: {len(all_results)}")
    print(f"Total reactions found: {total_reactions}")
    print(f"Successfully scraped: {total_successful}")
    print(f"Failed: {total_reactions - total_successful}")
    print(f"{'='*60}\n")
    
    return all_results


def main():
    # Get user configuration
    config = get_user_input()
    
    print("\n" + "="*60)
    print("STARTING SCRAPING WITH YOUR CONFIGURATION")
    print("="*60)
    print(f"Mode: {config['mode']}")
    print("="*60 + "\n")
    
    results = []

    # Execute based on mode
    if config['mode'] == 'all':
        results = scrape_all_datasets_parallel(
            max_workers=config['max_workers'],
            dataset_start=config.get('dataset_start'),
            dataset_end=config.get('dataset_end')
        )
    
    elif config['mode'] == 'specific_datasets':
        results = scrape_all_datasets_parallel(
            max_workers=config['max_workers'],
            specific_datasets=config['dataset_ids']
        )
    
    elif config['mode'] == 'uniform_range':
        results = scrape_all_datasets_parallel(
            max_workers=config['max_workers'],
            dataset_start=config.get('dataset_start'),
            dataset_end=config.get('dataset_end'),
            reaction_start=config.get('reaction_start'),
            reaction_end=config.get('reaction_end')
        )
    
    elif config['mode'] == 'custom_ranges':
        results = scrape_all_datasets_parallel(
            max_workers=config['max_workers'],
            dataset_ranges=config['dataset_ranges']
        )

    # --- NEW HANDLE FOR MODE 5 ---
    elif config['mode'] == 'single_target':
        # We achieve "single dataset, single reaction" by setting start=end
        d_target = config['dataset_target']
        r_target = config['reaction_target']
        
        results = scrape_all_datasets_parallel(
            max_workers=1,
            dataset_start=d_target,
            dataset_end=d_target,    # Start and End are same = 1 dataset
            reaction_start=r_target,
            reaction_end=r_target    # Start and End are same = 1 reaction
        )
    
    else:
        print("Invalid configuration!")
        return
    
    # --- OUTPUT AND SAVING (Keep your existing formatting code below) ---
    print("\n" + "="*60)
    print("SAMPLE FORMATTED DATA:")
    print("="*60)
    
    for dataset in results:
        if dataset.get('successful_scrapes', 0) > 0:
            print(f"\nDataset ID: {dataset['dataset_id']}")
            for reaction in dataset['reactions']:
                if reaction.get('success') and 'formatted_data' in reaction:
                    formatted = reaction['formatted_data']
                    print(f"  Reaction ID: {formatted['reaction_id']}")
                    
                    # Show inputs by tab
                    print("  Inputs by tab:")
                    for input_entry in formatted.get('inputsMap', []):
                        tab_name = input_entry[0]
                        input_data = input_entry[1]
                        print(f"    {tab_name}:")
                        
                        for component in input_data.get('components', []):
                            if component['identifiers']:
                                smiles = component['identifiers'][0]['value']
                                role = component['reaction_role']
                                
                                amount_info = ""
                                if 'moles' in component['amount']:
                                    moles = component['amount']['moles']['value']
                                    amount_info = f"moles: {moles}"
                                elif 'volume' in component['amount']:
                                    volume = component['amount']['volume']['value']
                                    amount_info = f"volume: {volume} L"
                                else:
                                    amount_info = "amount: N/A"
                                
                                print(f"      - {smiles}")
                                print(f"        reaction_role: {role}")
                                print(f"        {amount_info}")
                    
                    # Show products
                    print("\n    Products:")
                    for product in formatted.get('outcomes', []):
                        if product['identifiers']:
                            smiles = product['identifiers'][0]['value']
                            desired = " (DESIRED)" if product.get('is_desired_product') else ""
                            print(f"      - {smiles}{desired}")
                    
                    break
            break
    
    # Save results
    output_file = 'ord_reaction_data_single.json' if config['mode'] == 'single_target' else 'ord_reaction_data_2.json'
    
    formatted_results = {}
    for dataset in results:
        dataset_id = dataset['dataset_id']
        formatted_results[dataset_id] = {
            'dataset_id': dataset_id,
            'total_reactions': dataset['total_reactions'],
            'successful_scrapes': dataset['successful_scrapes'],
            'reactions': []
        }
        for reaction in dataset.get('reactions', []):
            if reaction.get('success') and 'formatted_data' in reaction:
                formatted_reaction = reaction['formatted_data']
                formatted_results[dataset_id]['reactions'].append(formatted_reaction)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(formatted_results, f, indent=2, ensure_ascii=False)
    print(f"\n✓ Formatted results saved to {output_file}")

if __name__ == "__main__":
    main()