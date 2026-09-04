import os
import sys

# Add current dir to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from analyzer import FileAnalyzer

def test():
    print("Initializing Analyzer...")
    analyzer = FileAnalyzer()
    
    # Create dummy files
    files = {
        "test_homework.txt": "This is a homework assignment for math class. Solve for x.",
        "test_secret.txt": "This is a top secret personal document. Passport number 12345.",
        "test_code.py": "print('Hello World')",
        "test_complex_code.py": "def complex_algo():\n" + "    pass\n" * 50
    }
    
    encoded_files = {}
    for name, content in files.items():
        path = os.path.abspath(name)
        with open(path, 'w') as f:
            f.write(content)
        encoded_files[name] = path
        
    # Check for image (from generate_image tool)
    img_path = os.path.abspath("test_receipt.png") # Assuming generate_image saves as png in cwd or artifacts? 
    # Actually generate_image saves to artifacts. I should check where it went.
    # For now let's just test text.
    
    print("Running Analysis...")
    for name, path in encoded_files.items():
        print(f"Analyzing {name}...")
        res = analyzer.analyze_file(path)
        print(f"Result: {manual_simplify(res)}")
        
    # Cleanup
    for path in encoded_files.values():
        os.remove(path)

def manual_simplify(res):
    return f"{res['importance']} (Score: {res['score']}) - {res['reasons']}"

if __name__ == "__main__":
    test()
