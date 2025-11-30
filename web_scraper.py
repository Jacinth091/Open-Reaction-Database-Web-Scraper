# driver = get_driver()
# driver.get("https://open-reaction-database.org/browse")

# dataset_links = driver.find_elements(By.XPATH, "//a[contains(@href, '/dataset/ord_dataset-')]")
# print("Dataset Links:", dataset_links )

# for link in dataset_links:
#   dataset_id = link.get_attribute('href').split('/')[-1]
#   print("Found Dataset: ", {dataset_id})

# print(driver.title)
# driver.quit()
import asyncio
from scraper_setup import get_driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

async def scrape_datasets_async():
  driver= get_driver()
  try:
    await asyncio.get_event_loop().run_in_executor(None, lambda: driver.get("https://open-reaction-database.org/browse"))
    wait = WebDriverWait(driver, 10)
    dataset_links = await asyncio.get_event_loop().run_in_executor(
        None, 
        lambda: wait.until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[href*='/dataset/ord_dataset-']"))  # FIXED: tuple format
        )
    )
    print(f"Found {len(dataset_links)} dataset links.")
    
    datasets = []
    for link in dataset_links:
      href = await asyncio.get_event_loop().run_in_executor(
        None, lambda: link.get_attribute('href') 
      )
      dataset_id = href.split('/')[-1]
      datasets.append(dataset_id)
      print("Found Dataset: ", {dataset_id})

    return datasets
  finally:
    await asyncio.get_event_loop().run_in_executor(None, driver.quit)
    


async def main():
    datasets = await scrape_datasets_async()
    print(f"Scraped {len(datasets)} datasets")

if __name__ == "__main__":
    asyncio.run(main())
    
    
    

