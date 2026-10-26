
from flask import Flask, render_template, request, jsonify
import joblib
import os
from news_search import search_news
from evidence_engine import analyze_evidence
from phishing_detector import predict_url

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

model = joblib.load(os.path.join(BASE_DIR, "model", "fake_news_model.pkl"))
vectorizer = joblib.load(os.path.join(BASE_DIR, "model", "vectorizer.pkl"))


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "").strip()

    if not text:
        return jsonify({
            "result": "No Content",
            "message": "Please enter a news article or claim."
        })

    try:
        text_vector = vectorizer.transform([text])
        prediction = model.predict(text_vector)[0]
        probabilities = model.predict_proba(text_vector)[0]
        confidence = round(max(probabilities) * 100, 2)

        news_results = search_news(text, max_results=10)
        evidence = analyze_evidence(
            news_results,
            claim=text,
            ml_prediction=prediction,
            ml_confidence=confidence
        )

        return jsonify({
            "result": evidence["verdict"],
            "message": evidence["explanation"],
            "confidence": confidence,
            "ml_label": evidence["ml_label"],
            "evidence_score": evidence["score"],
            "fact_checks": evidence["fact_checks"],
            "reasons": evidence["reasons"],
            "evidence_strength": evidence["evidence_strength"],
            "supporting_count": evidence.get("supporting_count", len(evidence["supporting_sources"])),
            "contradicting_count": evidence.get("contradicting_count", len(evidence["contradicting_sources"])),
            "neutral_count": evidence.get("neutral_count", len(evidence["other_sources"])),
            "supporting_sources": evidence["supporting_sources"],
            "contradicting_sources": evidence["contradicting_sources"],
            "other_sources": evidence["other_sources"],
            "credible_sources": evidence["credible_sources"],
            "independent_sources": evidence["independent_sources"],
            "sources": news_results
        })

    except Exception as error:
        app.logger.exception("Analysis failed")
        return jsonify({
            "result": "Analysis Error",
            "message": "Analysis failed. Check the Flask terminal for details."
        }), 500


@app.route("/check-url", methods=["POST"])
def check_url():
    data = request.get_json(silent=True) or {}
    url = str(data.get("url") or "").strip()

    if not url:
        return jsonify({
            "result": "No URL",
            "message": "Please enter a URL."
        })

    try:
        result = predict_url(url)
        return jsonify({
            "result": result["verdict"],
            "confidence": result["confidence"],
            "risk": result["risk"],
            "level": result["level"],
            "good": result["good"],
            "domain": result["domain"],
            "ml_probability": result["ml_probability"],
            "reasons": result["reasons"]
        })
    except Exception:
        app.logger.exception("URL check failed")
        return jsonify({
            "result": "Analysis Error",
            "message": "URL analysis failed. Check the Flask terminal for details."
        }), 500


@app.route("/health")
def health():
    """Quick check that the models and rules loaded (open in the browser)."""
    return jsonify({"status": "ok", "fake_news_model": type(model).__name__,
                    "vectorizer_terms": len(vectorizer.vocabulary_)})


if __name__ == "__main__":
    app.run(debug=True)
