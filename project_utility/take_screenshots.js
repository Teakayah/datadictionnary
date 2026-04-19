const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1280, height: 800 });

  console.log('Capturing Marketing Mockup...');
  await page.goto('http://127.0.0.1:8080/design_system/ui_kits/marketing/index.html');
  // Wait for React/Babel to render
  await page.waitForSelector('#root > *');
  await page.screenshot({ path: 'screenshots/marketing_mockup.png', fullPage: true });

  console.log('Capturing App Login Mockup...');
  await page.goto('http://127.0.0.1:8080/design_system/ui_kits/app/index.html');
  await page.waitForSelector('#root > *');
  await page.screenshot({ path: 'screenshots/app_login_mockup.png' });

  console.log('Capturing App Search Mockup...');
  await page.click('text=Sign in with Entra ID');
  await page.waitForSelector('text=Find your data');
  await page.screenshot({ path: 'screenshots/app_search_mockup.png' });

  console.log('Capturing App Table Detail Mockup...');
  // Click on a table row if available
  const row = page.locator('text=dim_customers'); 
  await row.waitFor();
  await row.click();
  await page.waitForSelector('text=§ Columns');
  await page.screenshot({ path: 'screenshots/app_detail_mockup.png' });

  await browser.close();
  console.log('Screenshots captured successfully.');
})();
