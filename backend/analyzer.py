import os
import time
import mimetypes
from datetime import datetime
from PIL import Image
from sentence_transformers import SentenceTransformer, util

# Constants
TEXT_MODEL_NAME = 'all-MiniLM-L6-v2'
IMAGE_MODEL_NAME = 'clip-ViT-B-32'

# Categories
IMPORTANCE_LEVELS = {
    'VERY_IMPORTANT': 3,
    'IMPORTANT': 2,
    'MODERATE': 1,
    'NOT_IMPORTANT': 0
}

class FileAnalyzer:
    def __init__(self):
        self.text_model = None
        self.image_model = None
        
    def _load_text_model(self):
        if not self.text_model:
            print("Loading Text Model...")
            self.text_model = SentenceTransformer(TEXT_MODEL_NAME)
            
    def _load_image_model(self):
        if not self.image_model:
            print("Loading Image Model...")
            self.image_model = SentenceTransformer(IMAGE_MODEL_NAME)

    def analyze_file(self, file_path):
        """
        Analyzes a file and returns (importance_level, confidence, reasons)
        """
        # 1. Metadata Check
        filename = os.path.basename(file_path)
        stats = os.stat(file_path)
        modified_time = datetime.fromtimestamp(stats.st_mtime)
        file_size = stats.st_size
        
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "unknown"

        # Initialize Base Score
        score = 0.5  # Neutral
        reasons = []
        
        # 2. Recency Check
        days_old = (datetime.now() - modified_time).days
        if days_old < 30:
            score += 0.2
            reasons.append("Recently modified (< 1 month)")
        elif days_old > 365:
            score -= 0.2
            reasons.append("Old file (> 1 year)")

        # 3. Content Analysis
        # Check for backup codes/important keywords in filename first
        lower_filename = filename.lower()
        if "backup" in lower_filename and ("code" in lower_filename or "key" in lower_filename or "recovery" in lower_filename):
            score += 2.0 # Boost significantly
            reasons.append("Filename indicates backup codes/keys")
        
        try:
            if mime_type.startswith('image/'):
                img_score, img_reason = self._analyze_image(file_path)
                score += img_score
                reasons.append(img_reason)
                
            elif mime_type.startswith('text/') or file_path.endswith(('.py', '.js', '.md', '.txt')):
                txt_score, txt_reason = self._analyze_text(file_path, filename)
                score += txt_score
                reasons.append(txt_reason)
                
            elif mime_type == 'application/pdf':
                # Simple heuristic for PDF for now (name based)
                if "receipt" in filename.lower() or "invoice" in filename.lower():
                    score += 0.8
                    reasons.append("Filename contains 'receipt' or 'invoice'")
                if "hw" in filename.lower() or "assignment" in filename.lower():
                    score -= 0.3
                    reasons.append("Filename suggests homework")
                    
        except Exception as e:
            reasons.append(f"Analysis failed: {str(e)}")

        # 4. Final Classification
        if score >= 1.2:
            importance = "Very Important"
        elif score >= 0.8:
            importance = "Important"
        elif score >= 0.4:
            importance = "Moderately Important"
        else:
            importance = "Not Important"

        return {
            "path": file_path,
            "filename": filename,
            "importance": importance,
            "score": round(score, 2),
            "reasons": "; ".join(reasons),
            "mime_type": mime_type,
            "modified": modified_time.isoformat(),
            "size_bytes": file_size
        }

    def _analyze_image(self, path):
        self._load_image_model()
        try:
            image = Image.open(path)
            # Define prompts
            prompts = ["A passport or ID card", "A receipt or invoice", "A family photo", "A screenshot", "A meme"]
            encoded_image = self.image_model.encode(image)
            encoded_prompts = self.image_model.encode(prompts)
            
            cos_sim = util.cos_sim(encoded_image, encoded_prompts)[0]
            
            # Find best match
            best_idx = cos_sim.argmax()
            best_label = prompts[best_idx]
            confidence = cos_sim[best_idx].item()
            
            if best_label in ["A passport or ID card", "A receipt or invoice"]:
                return 0.9, f"Visual match: {best_label} ({confidence:.2f})"
            elif best_label == "A family photo":
                return 0.7, f"Visual match: {best_label} ({confidence:.2f})"
            elif best_label == "A meme":
                return -0.5, f"Visual match: {best_label}"
            
            return 0.0, f"Image classified as {best_label}"
            
        except Exception as e:
            return 0.0, f"Image error: {str(e)}"

    def _analyze_text(self, path, filename):
        # Code novelty check
        if path.endswith(('.py', '.js', '.ts', '.rs')):
            with open(path, 'r', errors='ignore') as f:
                content = f.read(2000) # Read first 2k chars
            
            if len(content) < 100:
                return -0.3, "Tiny code file"
            if "TODO" in content and len(content) < 500:
                return -0.1, "Likely incomplete/boilerplate"
                
            return 0.3, "Source code file"

        # General text content
        self._load_text_model()
        try:
            with open(path, 'r', errors='ignore') as f:
                content = f.read(1000)
            
            if not content.strip():
                 return -0.5, "Empty file"

            prompts = ["Important personal document", "School homework assignment", "Creative writing", "Log file or system output"]
            
            emb_content = self.text_model.encode(content)
            emb_prompts = self.text_model.encode(prompts)
            
            cos_sim = util.cos_sim(emb_content, emb_prompts)[0]
            best_idx = cos_sim.argmax()
            best_label = prompts[best_idx]
            
            if best_label == "Important personal document":
                return 0.7, "Content looks like personal doc"
            elif best_label == "School homework assignment":
                return -0.2, "Content looks like homework"
            elif best_label == "Log file or system output":
                 return -0.5, "Log file"
                 
            return 0.0, f"Content classified as {best_label}"
            
        except Exception as e:
            return 0.0, f"Text error: {str(e)}"
