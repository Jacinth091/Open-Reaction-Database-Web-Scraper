from scraper_setup import get_driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import time

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
    dataset_ids = dataset_ids[:1]  # Start with just 1 datasets
    
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

def main():
    results = scrape_all_datasets_sequential()

if __name__ == "__main__":
    main()