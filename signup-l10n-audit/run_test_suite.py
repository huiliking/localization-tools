"""
Automated Test Runner for Sign-Up Localization Audit
Tests multiple sites and generates summary report
"""

import subprocess
import sys
from datetime import datetime

class TestRunner:
    def __init__(self, output_file=None):
        self.output_file = output_file or f"audit_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        self.results = []
        
    def run_test(self, site_url, locale='es'):
        """Run audit test for a single site"""
        print(f"\n{'='*70}")
        print(f"Testing: {site_url}")
        print(f"Locale: {locale}")
        print(f"{'='*70}\n")
        
        try:
            # Run the audit script
            process = subprocess.Popen(
                ['python', 'signup_localization_audit_v2_integrated.py'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Send inputs
            stdout, stderr = process.communicate(input=f"{site_url}\n{locale}\n\n", timeout=120)
            
            # Parse results
            result = self.parse_output(site_url, stdout)
            self.results.append(result)
            
            return stdout, stderr
        
        except subprocess.TimeoutExpired:
            print(f"✗ Test timed out for {site_url}")
            self.results.append({
                'site': site_url,
                'status': 'TIMEOUT',
                'error': 'Test exceeded 120 seconds'
            })
            return None, "Timeout"
        
        except Exception as e:
            print(f"✗ Error testing {site_url}: {e}")
            self.results.append({
                'site': site_url,
                'status': 'ERROR',
                'error': str(e)
            })
            return None, str(e)
    
    def parse_output(self, site_url, output):
        """Parse test output to extract key results"""
        result = {
            'site': site_url,
            'status': 'UNKNOWN',
            'llm_response': None,
            'button_found': None,
            'button_text': None,
            'signup_tested': False,
            'tests_passed': 0,
            'tests_total': 0
        }
        
        lines = output.split('\n')
        
        for line in lines:
            # Extract LLM response
            if '[DEBUG] LLM raw response:' in line:
                result['llm_response'] = line.split("'")[1] if "'" in line else line.split(':')[1].strip()
            
            # Extract button found
            if '✓ LLM selected #' in line or '✓ Fallback matched' in line:
                result['button_found'] = 'LLM' if 'LLM selected' in line else 'FALLBACK'
                if ':' in line:
                    result['button_text'] = line.split("'")[1] if "'" in line else None
            
            # Check if signup button was found
            if '✓ Found signup button:' in line:
                result['signup_tested'] = True
                if "'" in line:
                    result['button_text'] = line.split("'")[1]
            
            if '✗ Could not identify signup button' in line:
                result['button_found'] = 'NONE'
            
            # Extract test results
            if 'Overall:' in line and 'tests passed' in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if '/' in part:
                        passed, total = part.split('/')
                        result['tests_passed'] = int(passed)
                        result['tests_total'] = int(total)
            
            # Extract final verdict
            if '✓ EXCELLENT:' in line:
                result['status'] = 'EXCELLENT'
            elif '⚠ PARTIAL:' in line:
                result['status'] = 'PARTIAL'
            elif '✗ POOR:' in line:
                result['status'] = 'POOR'
        
        return result
    
    def write_results(self, full_output=None):
        """Write results to output file"""
        with open(self.output_file, 'w', encoding='utf-8') as f:
            f.write("="*70 + "\n")
            f.write("SIGN-UP LOCALIZATION AUDIT - TEST SUITE RESULTS\n")
            f.write("="*70 + "\n")
            f.write(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Target Locale: Spanish (es)\n")
            f.write("="*70 + "\n\n")
            
            # Summary table
            f.write("SUMMARY TABLE\n")
            f.write("-"*70 + "\n")
            f.write(f"{'Site':<25} {'Button Found':<15} {'Method':<12} {'Status':<10}\n")
            f.write("-"*70 + "\n")
            
            for result in self.results:
                site = result['site'][:24]
                button = result['button_text'][:14] if result['button_text'] else 'NOT FOUND'
                method = result['button_found'] or 'N/A'
                status = result['status']
                
                f.write(f"{site:<25} {button:<15} {method:<12} {status:<10}\n")
            
            f.write("-"*70 + "\n\n")
            
            # Detailed results
            f.write("DETAILED RESULTS\n")
            f.write("="*70 + "\n\n")
            
            for i, result in enumerate(self.results, 1):
                f.write(f"TEST {i}: {result['site']}\n")
                f.write("-"*70 + "\n")
                f.write(f"Status: {result['status']}\n")
                f.write(f"LLM Response: {result['llm_response']}\n")
                f.write(f"Button Found: {result['button_found']}\n")
                f.write(f"Button Text: {result['button_text']}\n")
                f.write(f"Signup Tested: {'Yes' if result['signup_tested'] else 'No'}\n")
                f.write(f"Tests Passed: {result['tests_passed']}/{result['tests_total']}\n")
                f.write("\n")
            
            # Statistics
            f.write("="*70 + "\n")
            f.write("STATISTICS\n")
            f.write("-"*70 + "\n")
            
            total_tests = len(self.results)
            llm_success = sum(1 for r in self.results if r['button_found'] == 'LLM')
            fallback_success = sum(1 for r in self.results if r['button_found'] == 'FALLBACK')
            failures = sum(1 for r in self.results if r['button_found'] == 'NONE' or r['button_found'] is None)
            
            f.write(f"Total Sites Tested: {total_tests}\n")
            f.write(f"LLM Success: {llm_success} ({llm_success/total_tests*100:.1f}%)\n")
            f.write(f"Fallback Success: {fallback_success} ({fallback_success/total_tests*100:.1f}%)\n")
            f.write(f"Failures: {failures} ({failures/total_tests*100:.1f}%)\n")
            f.write(f"Overall Success Rate: {(llm_success+fallback_success)/total_tests*100:.1f}%\n")
            f.write("="*70 + "\n")
            
            # Full output if provided
            if full_output:
                f.write("\n\n")
                f.write("="*70 + "\n")
                f.write("FULL TEST OUTPUT\n")
                f.write("="*70 + "\n\n")
                f.write(full_output)
    
    def print_summary(self):
        """Print summary to console"""
        print("\n" + "="*70)
        print("TEST SUITE SUMMARY")
        print("="*70)
        print(f"{'Site':<25} {'Button Found':<15} {'Method':<12} {'Status':<10}")
        print("-"*70)
        
        for result in self.results:
            site = result['site'][:24]
            button = result['button_text'][:14] if result['button_text'] else 'NOT FOUND'
            method = result['button_found'] or 'N/A'
            status = result['status']
            
            print(f"{site:<25} {button:<15} {method:<12} {status:<10}")
        
        print("-"*70)
        
        total = len(self.results)
        llm = sum(1 for r in self.results if r['button_found'] == 'LLM')
        fallback = sum(1 for r in self.results if r['button_found'] == 'FALLBACK')
        failures = sum(1 for r in self.results if r['button_found'] in ['NONE', None])
        
        print(f"\nLLM Success: {llm}/{total} ({llm/total*100:.1f}%)")
        print(f"Fallback Success: {fallback}/{total} ({fallback/total*100:.1f}%)")
        print(f"Failures: {failures}/{total} ({failures/total*100:.1f}%)")
        print(f"Overall Success: {(llm+fallback)/total*100:.1f}%")
        print("="*70)


if __name__ == "__main__":
    # Test sites - comprehensive suite
    sites = [
        # Original 4 sites
        'www.shopify.com',
        'www.stripe.com',
        'www.amazon.com',
        'www.bbc.com',
        # New 6 sites
        'www.netflix.com',
        'www.walmart.com',
        'www.cnn.com',
        'www.openai.com',
        'www.microsoft.com',
        'www.anthropic.com',  # Save the best for last!
    ]
    
    print("""
====================================================================
      AUTOMATED SIGN-UP LOCALIZATION AUDIT TEST SUITE
                    FINAL RUN - 10 SITES
====================================================================
    """)
    
    runner = TestRunner()
    
    full_output = []
    
    for i, site in enumerate(sites, 1):
        print(f"\n[{i}/{len(sites)}] Testing {site}...")
        stdout, stderr = runner.run_test(site, locale='es')
        
        if stdout:
            full_output.append(f"\n{'='*70}\n")
            full_output.append(f"TEST {i}: {site}\n")
            full_output.append(f"{'='*70}\n")
            full_output.append(stdout)
    
    # Print summary
    runner.print_summary()
    
    # Write results
    runner.write_results(full_output=''.join(full_output))
    
    print(f"\nResults saved to: {runner.output_file}")
    print("\nOpening results file...")
    
    # Open results file
    import os
    os.startfile(runner.output_file)
