document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('predictionForm');
    const predictBtn = document.getElementById('predictBtn');
    const loader = document.getElementById('loader');
    const errorBox = document.getElementById('errorBox');
    const resultsSection = document.getElementById('resultsSection');
    
    const resScore = document.getElementById('resScore');
    const resCategory = document.getElementById('resCategory');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        // Collect form data
        const formData = new FormData(form);
        const data = {
            "heart_rate_bpm": parseFloat(formData.get('heart_rate_bpm')),
            "spo2_percent": parseFloat(formData.get('spo2_percent')),
            "temperature_c": parseFloat(formData.get('temperature_c')),
            "resp_rate_min": parseFloat(formData.get('resp_rate_min')),
            "crp_mg_l": parseFloat(formData.get('crp_mg_l')),
            // The original column name has \u10e9, so we send it exactly as expected
            "wbc\u10e9l": parseFloat(formData.get('wbc_l')),
            "gestational_age_weeks": parseFloat(formData.get('gestational_age_weeks')),
            "birth_weight_g": parseFloat(formData.get('birth_weight_g'))
        };

        // UI states
        predictBtn.disabled = true;
        loader.style.display = 'block';
        errorBox.style.display = 'none';
        resultsSection.style.display = 'none';

        try {
            const response = await fetch('/predict_form', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data)
            });

            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.error || 'Something went wrong');
            }

            renderResults(result);
            resultsSection.style.display = 'block';

        } catch (err) {
            errorBox.textContent = err.message;
            errorBox.style.display = 'block';
        } finally {
            loader.style.display = 'none';
            predictBtn.disabled = false;
        }
    });

    function renderResults(result) {
        // Format percentage
        const scorePercent = (result.risk_score * 100).toFixed(2) + '%';
        resScore.textContent = scorePercent;
        
        // Badge class
        let badgeClass = '';
        if (result.risk_category === 'Low Risk') badgeClass = 'badge-low';
        else if (result.risk_category === 'Moderate Risk') badgeClass = 'badge-mod';
        else badgeClass = 'badge-high';

        resCategory.textContent = result.risk_category;
        resCategory.className = `badge ${badgeClass}`;
    }
});
