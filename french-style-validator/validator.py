import click
import re
from pathlib import Path

def check_vpn_translation(content):
    """VPN should never be translated to RVP in French."""
    issues = []
    if "RVP" in content:
        issues.append("❌ Found 'RVP' - should be 'VPN' in French")
    return issues


def check_missing_accents_on_capitals(content):
    """Check for capital letters that should be accented in French."""
    issues = []
    
    # Dictionary of unaccented words -> correct accented versions
    words_needing_accents = {
        'A': 'À',  # when used as preposition "à"
        'Etat': 'État',
        'Etats': 'États',
        'Etre': 'Être',
        'Ecole': 'École',
        'Eglise': 'Église',
        'Electricite': 'Électricité',
        'Electricien': 'Électricien',
        'Electrique': 'Électrique',
        'Energie': 'Énergie',
        'Etude': 'Étude',
        'Etudes': 'Études',
        'Economie': 'Économie',
        'Economique': 'Économique',
        'Eleve': 'Élève',
        'Eleves': 'Élèves',
        'Episode': 'Épisode',
        'Equipe': 'Équipe',
        'Equipement': 'Équipement',
        'Evenement': 'Événement',
        'Evenements': 'Événements',
        'Ere': 'Ère',
    }
    
    lines = content.split('\n')
    for line_num, line in enumerate(lines, 1):
        for wrong_word, correct_word in words_needing_accents.items():
            # Use word boundaries to match whole words
            pattern = r'\b' + re.escape(wrong_word) + r'\b'
            matches = re.finditer(pattern, line)
            
            for match in matches:
                pos = match.start()
                # Get context
                start = max(0, pos - 20)
                end = min(len(line), pos + len(wrong_word) + 20)
                context = line[start:end]
                
                issue = (f"❌ Line {line_num}: Found '{wrong_word}' "
                        f"(should be '{correct_word}') - Context: ...{context}...")
                issues.append(issue)
    
    return issues


def check_translated_paths(filename):
    """
    Check for translated Windows paths in the file.
    
    Args:
        filename (str): Path to the file to check
        
    Returns:
        list: List of issues found (formatted strings)
    """
    issues = []
    
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            for line_num, line in enumerate(file, 1):
                paths = extract_paths_from_line(line)
                
                for path in paths:
                    if is_path_translated(path):
                        issue = f"❌ Line {line_num}: Translated path '{path}'"
                        issues.append(issue)
                        
    except FileNotFoundError:
        issues.append(f"Error: File '{filename}' not found.")
    except Exception as e:
        issues.append(f"Error reading file: {e}")
    
    return issues


def is_path_translated(path_string):
    """
    Check if a Windows path contains translated (non-English) components.
    
    Args:
        path_string (str): The path to check
        
    Returns:
        bool: True if path contains translated components, False otherwise
    """
    # Common English Windows path terms that should NOT be flagged
    english_terms = {
        'program files', 'common files', 'windows', 'system32', 'users',
        'appdata', 'local', 'roaming', 'temp', 'documents', 'desktop',
        'downloads', 'pictures', 'music', 'videos', 'public', 'programdata',
        'microsoft', 'mcafee', 'intel', 'nvidia', 'amd'
    }
    
    # Split path into components
    path_parts = Path(path_string).parts
    
    for part in path_parts:
        # Skip drive letters (e.g., 'C:')
        if re.match(r'^[A-Za-z]:$', part):
            continue
            
        # Convert to lowercase for comparison
        part_lower = part.lower()
        
        # Check if it's a known English term
        if part_lower in english_terms:
            continue
            
        # Check for non-ASCII characters (common in translations)
        if not part.isascii():
            return True
            
        # Check for angle brackets which often indicate placeholders/translations
        if '<' in part or '>' in part:
            return True
            
        # Check for common translation patterns (hyphens in unexpected places)
        # This catches things like "nom-serveur"
        if '-' in part_lower and part_lower not in english_terms:
            # Allow common hyphenated English terms
            common_hyphenated = ['x86', 'x64', 'add-ons', 'add-ins']
            if not any(term in part_lower for term in common_hyphenated):
                return True
    
    return False


def extract_paths_from_line(line):
    """
    Extract Windows paths from a line of text.
    
    Args:
        line (str): Line of text to search for paths
        
    Returns:
        list: List of paths found in the line
    """
    # Pattern to match Windows paths (drive letter followed by path)
    # Modified to allow more characters including <>, non-ASCII
    pattern = r'[A-Za-z]:[/\\](?:[^:\*\?"\|\r\n]+)'
    
    matches = re.findall(pattern, line)
    
    # Clean up matches - remove trailing spaces and punctuation
    cleaned_paths = []
    for match in matches:
        # Remove trailing whitespace and common punctuation
        cleaned = match.rstrip(' \t,;.')
        if cleaned:
            cleaned_paths.append(cleaned)
    
    return cleaned_paths


@click.command()
@click.argument('input_file')
def validate(input_file):
    """Validate French translations against style guide rules."""
    click.echo(f"Validating: {input_file}")
    
    # Read the file
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    click.echo(f"✓ Read {len(content)} characters\n")
    
    # Run validation rules
    all_issues = []
    
    # Rule 1: VPN/RVP check
    click.echo("Rule 1: Checking VPN translation...")
    vpn_issues = check_vpn_translation(content)
    if vpn_issues:
        click.echo(f"  ❌ Found {len(vpn_issues)} issue(s)")
    else:
        click.echo("  ✓ Passed")
    all_issues.extend(vpn_issues)
    
    # Rule 2: Missing accents on capital letters check
    click.echo("Rule 2: Checking for missing accents on capitals...")
    accent_issues = check_missing_accents_on_capitals(content)
    if accent_issues:
        click.echo(f"  ❌ Found {len(accent_issues)} issue(s)")
    else:
        click.echo("  ✓ Passed")
    all_issues.extend(accent_issues)
    
    # Rule 3: Translated paths check
    click.echo("Rule 3: Checking for translated paths...")
    path_issues = check_translated_paths(input_file)
    if path_issues:
        click.echo(f"  ❌ Found {len(path_issues)} issue(s)")
    else:
        click.echo("  ✓ Passed")
    all_issues.extend(path_issues)
    
    # Report results
    click.echo("\n" + "="*80)
    if all_issues:
        click.echo("VALIDATION FAILED - Issues found:")
        click.echo("="*80)
        for issue in all_issues:
            click.echo(f"  {issue}")
    else:
        click.echo("✓ VALIDATION PASSED - No issues found!")
    
    click.echo("\n" + "="*80)
    click.echo(f"Total issues: {len(all_issues)}")
    click.echo("="*80)


if __name__ == '__main__':
    validate()
