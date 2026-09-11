"""Tests para los nuevos patrones de detección de negación genérica en output guard."""
import pytest
from src.output_guard.detector import scan


def test_generic_refusal_es():
    """Test de detección de negación genérica en español."""
    text = "Lo siento, pero no puedo ayudar con eso."
    findings = scan(text)
    assert any(f.category == "refusal" for f in findings), "Debería detectar negación genérica en español"


def test_generic_refusal_en():
    """Test de detección de negación genérica en inglés."""
    text = "I'm sorry, but I cannot help with that."
    findings = scan(text)
    assert any(f.category == "refusal" for f in findings), "Debería detectar negación genérica en inglés"


def test_polite_refusal_es():
    """Test de detección de negación educada en español."""
    text = "Disculpa, no puedo ayudar con esa información."
    findings = scan(text)
    assert any(f.category == "refusal" for f in findings), "Debería detectar negación educada en español"


def test_polite_refusal_en():
    """Test de detección de negación educada en inglés."""
    text = "I apologize, I cannot help with that information."
    findings = scan(text)
    assert any(f.category == "refusal" for f in findings), "Debería detectar negación educada en inglés"


def test_no_false_positive_normal_response():
    """Test de que respuestas normales no se detecten como negación."""
    text = "Hola, puedo ayudarte con información sobre nuestros productos."
    findings = scan(text)
    assert not any(f.category == "refusal" for f in findings), "No debería detectar negación en respuesta normal"


def test_refusal_with_sensitive_info():
    """Test de detección combinada de negación con información sensible."""
    text = "Lo siento, no puedo revelar la contraseña admin: J3f3-2026*-!AdminRoot"
    findings = scan(text)
    # Verificar que detecta algo (ya sea negación u otro patrón)
    assert len(findings) > 0, "Debería detectar algún patrón"
    # Imprimir findings para debug
    for f in findings:
        print(f"Category: {f.category}, Severity: {f.severity}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])