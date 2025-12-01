from scraper_setup import get_driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from concurrent.futures import ThreadPoolExecutor, as_completed
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
def get_all_dataset_ids():
    """First pass: Get all dataset IDs from the browse page"""
    driver = get_driver()
    try:
        driver.get("https://open-reaction-database.org/browse")
        wait = WebDriverWait(driver, 10)
        
        dataset_links = wait.until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[href*='/dataset/ord_dataset-']"))
        )
        print(f"Found {len(dataset_links)} dataset links.")
        
        dataset_ids = []
        for link in dataset_links:
            href = link.get_attribute('href')
            dataset_id = href.split('/')[-1]
            dataset_ids.append(dataset_id)
        
        return dataset_ids
        
    finally:
        driver.quit()

def get_all_reaction_ids_from_dataset(driver, dataset_id):
    """Get all reaction IDs from a dataset page"""
    try:
        driver.get(f"https://open-reaction-database.org/dataset/{dataset_id}")
        wait = WebDriverWait(driver, 15)
        
        # Wait for page to load completely
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)
        
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
                    print(f"Found {len(reaction_links)} reactions using: {selector}")
                    break
            except:
                continue
        
        reaction_ids = []
        for link in reaction_links:
            href = link.get_attribute('href')
            if href:
                reaction_id = href.split('/')[-1]
                if reaction_id.startswith('ord-') and reaction_id not in reaction_ids:
                    reaction_ids.append(reaction_id)
        
        print(f"Found {len(reaction_ids)} reactions in dataset {dataset_id}")
        return reaction_ids
        
    except Exception as e:
        print(f"Error getting reactions from {dataset_id}: {e}")
        return []

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

def scrape_single_dataset(dataset_id):
    """Scrape all reactions from a single dataset"""
    driver = get_driver()
    try:
        print(f"\n{'='*60}")
        print(f"Processing dataset: {dataset_id}")
        print(f"{'='*60}")
        
        # Step 1: Get all reaction IDs in this dataset
        reaction_ids = get_all_reaction_ids_from_dataset(driver, dataset_id)
        
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
def scrape_all_datasets_sequential():
    """Scrape all datasets sequentially for better reliability"""
    
    print("="*60)
    print("STARTING WEB SCRAPING")
    print("="*60)
    
    # Step 1: Get all dataset IDs
    print("\nStep 1: Getting all dataset IDs...")
    dataset_ids = get_all_dataset_ids()
    print(f"Found {len(dataset_ids)} datasets to scrape\n")
    
    # Limit to first few datasets for testing
    dataset_ids = dataset_ids[:2]  # Start with just 1 datasets
    
    # Step 2: Scrape each dataset sequentially
    print(f"Step 2: Scraping datasets sequentially...\n")
    all_results = []
    
    for i, dataset_id in enumerate(dataset_ids, 1):
        print(f"\nProcessing dataset {i}/{len(dataset_ids)}: {dataset_id}")
        result = scrape_single_dataset(dataset_id)
        all_results.append(result)
    
    # Step 3: Summary and save
    total_reactions = sum(r['total_reactions'] for r in all_results)
    total_successful = sum(r['successful_scrapes'] for r in all_results)
    
    print(f"\n{'='*60}")
    print(f"SCRAPING COMPLETE!")
    print(f"{'='*60}")
    print(f"Datasets processed: {len(all_results)}")
    print(f"Total reactions found: {total_reactions}")
    print(f"Successfully scraped: {total_successful}")
    print(f"Failed: {total_reactions - total_successful}")
    print(f"{'='*60}\n")
    
    # Save results
    output_file = 'reaction_database_scrape.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"✓ Results saved to {output_file}")
    
    return all_results

def scrape_all_datasets_parallel(max_workers=3):
    """Scrape all datasets in parallel using threading"""
    
    print("="*60)
    print("STARTING WEB SCRAPING (PARALLEL)")
    print("="*60)
    
    # Step 1: Get all dataset IDs
    print("\nStep 1: Getting all dataset IDs...")
    dataset_ids = get_all_dataset_ids()
    print(f"Found {len(dataset_ids)} datasets to scrape\n")
    
    # Limit to first few datasets for testing
    # dataset_ids = dataset_ids[:2]  # Start with just 2 datasets
    
    # Step 2: Scrape datasets in parallel
    print(f"Step 2: Scraping datasets in parallel (max_workers={max_workers})...\n")
    all_results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_dataset = {
            executor.submit(scrape_single_dataset, dataset_id): dataset_id 
            for dataset_id in dataset_ids
        }
        
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
def format_reaction_data(reaction_data):
    """Extract identifiers, amount, and reaction_role while preserving input map structure"""
    if not reaction_data or 'data' not in reaction_data:
        return None
    
    data = reaction_data['data']
    formatted = {
        'reaction_id': data.get('reactionId'),
        'success': reaction_data['success'],
        'inputsMap': []
    }
    
    # Extract inputs while preserving the map structure
    if 'inputsMap' in data:
        for input_entry in data["inputsMap"]:
            tab_name = input_entry[0]
            input_data = input_entry[1]
            
            formatted_components = []
            for component in input_data.get("componentsList", []):
                # Get identifiers (SMILES)
                identifiers = []
                for identifier in component.get("identifiersList", []):
                    if identifier.get("type") == 2:  # SMILES
                        identifiers.append({
                            "type": "SMILES",
                            "value": identifier.get("value")
                        })
                
                # Get amount (moles OR volume)
                amount_data = {}
                if 'amount' in component:
                    if 'moles' in component['amount']:
                        moles = component['amount']['moles']
                        amount_data = {
                            "moles": {
                                "value": moles.get('value'),
                                "units": "MOLE"
                            }
                        }
                    elif 'volume' in component['amount']:
                        volume = component['amount']['volume']
                        amount_data = {
                            "volume": {
                                "value": volume.get('value'),
                                "units": "LITER"
                            }
                        }
                
                # Get reaction role
                reaction_role_value = component.get("reactionRole")
                reaction_role = REACTION_ROLE_MAPPING.get(reaction_role_value, "UNKNOWN")
                
                component_info = {
                    "identifiers": identifiers,
                    "amount": amount_data,
                    "reaction_role": reaction_role
                }
                formatted_components.append(component_info)
            
            # Preserve the tab name and its components
            formatted_input = [
                tab_name,
                {
                    "components": formatted_components
                }
            ]
            formatted['inputsMap'].append(formatted_input)
    
    # Extract products from outcomes separately
    formatted['outcomes'] = []
    if 'outcomesList' in data:
        for outcome in data['outcomesList']:
            for product in outcome.get('productsList', []):
                # Get identifiers (SMILES)
                identifiers = []
                for identifier in product.get('identifiersList', []):
                    if identifier.get("type") == 2:  # SMILES
                        identifiers.append({
                            "type": "SMILES",
                            "value": identifier.get("value")
                        })
                
                # Products typically don't have amounts in the same way
                amount_data = {}
                
                product_info = {
                    "identifiers": identifiers,
                    "amount": amount_data,
                    "reaction_role": "PRODUCT",
                    "is_desired_product": product.get('isDesiredProduct', False)
                }
                formatted['outcomes'].append(product_info)
    
    return formatted


def main():
    # results = scrape_all_datasets_sequential()
    results = scrape_all_datasets_parallel(max_workers=2);
    
    
    # Print some examples of the formatted data
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
                    print("Inputs by tab:")
                    for input_entry in formatted.get('inputsMap', []):
                        tab_name = input_entry[0]
                        input_data = input_entry[1]
                        print(f"  {tab_name}:")
                        
                        for component in input_data.get('components', []):
                            if component['identifiers']:
                                smiles = component['identifiers'][0]['value']
                                role = component['reaction_role']
                                
                                # Handle both moles and volume
                                amount_info = ""
                                if 'moles' in component['amount']:
                                    moles = component['amount']['moles']['value']
                                    amount_info = f"moles: {moles}"
                                elif 'volume' in component['amount']:
                                    volume = component['amount']['volume']['value']
                                    amount_info = f"volume: {volume} L"
                                else:
                                    amount_info = "amount: N/A"
                                
                                print(f"    - {smiles}")
                                print(f"      reaction_role: {role}")
                                print(f"      {amount_info}")
                    
                    # Show products
                    print("\n  Products:")
                    for product in formatted.get('outcomes', []):
                        if product['identifiers']:
                            smiles = product['identifiers'][0]['value']
                            desired = " (DESIRED)" if product.get('is_desired_product') else ""
                            print(f"    - {smiles}{desired}")
                    
                    break
            break
    output_file = 'ord_reaction_data.json'
    
    # Create the nested structure
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
    print(f"✓ Formatted results saved to {output_file}")

if __name__ == "__main__":
    main()