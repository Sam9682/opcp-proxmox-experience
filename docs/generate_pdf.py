#!/usr/bin/env python3
"""Generate a marketing-style PDF from the OPCP Proxmox GPU Passthrough content."""

from weasyprint import HTML

html_content = """
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<style>
@page {
    size: A4;
    margin: 0;
}

body {
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    margin: 0;
    padding: 0;
    color: #2c3e50;
    line-height: 1.6;
}

/* Cover Page */
.cover {
    height: 297mm;
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    text-align: center;
    color: white;
    padding: 60px;
    page-break-after: always;
}

.cover h1 {
    font-size: 42px;
    font-weight: 700;
    margin-bottom: 20px;
    letter-spacing: -0.5px;
}

.cover .subtitle {
    font-size: 22px;
    font-weight: 300;
    opacity: 0.9;
    margin-bottom: 40px;
}

.cover .tagline {
    font-size: 16px;
    font-weight: 300;
    opacity: 0.7;
    border-top: 1px solid rgba(255,255,255,0.3);
    padding-top: 30px;
    margin-top: 40px;
}

.cover .brand {
    font-size: 18px;
    font-weight: 600;
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-top: 60px;
    opacity: 0.8;
}

/* Content Pages */
.page {
    padding: 50px 60px;
    page-break-after: always;
}

.page:last-child {
    page-break-after: avoid;
}

h2 {
    font-size: 28px;
    color: #0f3460;
    font-weight: 700;
    margin-bottom: 25px;
    padding-bottom: 10px;
    border-bottom: 3px solid #e94560;
}

h3 {
    font-size: 20px;
    color: #16213e;
    font-weight: 600;
    margin-top: 30px;
    margin-bottom: 15px;
}

p {
    font-size: 14px;
    margin-bottom: 15px;
    color: #444;
}

.intro-text {
    font-size: 16px;
    color: #555;
    line-height: 1.8;
    margin-bottom: 30px;
}

/* Feature Cards */
.features {
    display: flex;
    flex-wrap: wrap;
    gap: 20px;
    margin: 30px 0;
}

.feature-card {
    background: #f8f9fa;
    border-radius: 12px;
    padding: 25px;
    width: 45%;
    border-left: 4px solid #e94560;
}

.feature-card h4 {
    font-size: 16px;
    color: #0f3460;
    margin: 0 0 10px 0;
    font-weight: 600;
}

.feature-card p {
    font-size: 13px;
    color: #666;
    margin: 0;
}

/* Benefits List */
.benefits {
    list-style: none;
    padding: 0;
}

.benefits li {
    font-size: 15px;
    padding: 12px 0 12px 35px;
    position: relative;
    border-bottom: 1px solid #eee;
}

.benefits li::before {
    content: "✓";
    position: absolute;
    left: 0;
    color: #e94560;
    font-weight: 700;
    font-size: 18px;
}

/* Timeline */
.timeline {
    margin: 30px 0;
}

.timeline-item {
    display: flex;
    align-items: flex-start;
    margin-bottom: 20px;
}

.timeline-badge {
    background: #0f3460;
    color: white;
    width: 40px;
    height: 40px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 14px;
    margin-right: 20px;
    flex-shrink: 0;
}

.timeline-content {
    flex: 1;
}

.timeline-content h4 {
    margin: 0 0 5px 0;
    font-size: 16px;
    color: #16213e;
}

.timeline-content p {
    margin: 0;
    font-size: 13px;
    color: #666;
}

/* Modules Grid */
.modules-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 15px;
    margin: 25px 0;
}

.module-card {
    background: linear-gradient(135deg, #f8f9fa, #e9ecef);
    border-radius: 10px;
    padding: 20px;
    width: 44%;
    text-align: center;
}

.module-card .module-number {
    background: #e94560;
    color: white;
    width: 30px;
    height: 30px;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 14px;
    margin-bottom: 10px;
}

.module-card h4 {
    font-size: 15px;
    color: #0f3460;
    margin: 8px 0;
}

.module-card p {
    font-size: 12px;
    color: #666;
    margin: 0;
}

/* CTA Section */
.cta {
    background: linear-gradient(135deg, #0f3460, #16213e);
    border-radius: 15px;
    padding: 40px;
    text-align: center;
    color: white;
    margin-top: 40px;
}

.cta h3 {
    color: white;
    font-size: 24px;
    margin: 0 0 15px 0;
}

.cta p {
    color: rgba(255,255,255,0.8);
    font-size: 15px;
    margin-bottom: 25px;
}

.cta .contact {
    font-size: 18px;
    font-weight: 600;
    color: #e94560;
}

/* Highlight Box */
.highlight-box {
    background: linear-gradient(135deg, #fff3f5, #ffeef0);
    border: 1px solid #e94560;
    border-radius: 12px;
    padding: 25px;
    margin: 25px 0;
}

.highlight-box h4 {
    color: #e94560;
    margin: 0 0 10px 0;
    font-size: 16px;
}

/* Environment section */
.env-cards {
    display: flex;
    gap: 20px;
    margin: 25px 0;
}

.env-card {
    flex: 1;
    background: white;
    border: 2px solid #e9ecef;
    border-radius: 12px;
    padding: 25px;
    text-align: center;
}

.env-card h4 {
    color: #0f3460;
    font-size: 16px;
    margin: 0 0 15px 0;
}

.env-card ul {
    text-align: left;
    padding-left: 20px;
    font-size: 13px;
    color: #666;
}

.env-card ul li {
    margin-bottom: 8px;
}

/* Footer */
.footer {
    text-align: center;
    padding: 20px;
    font-size: 11px;
    color: #999;
    margin-top: 40px;
}
</style>
</head>
<body>

<!-- COVER PAGE -->
<div class="cover">
    <h1>OPCP Proxmox VE<br>GPU Passthrough</h1>
    <div class="subtitle">Déploiement automatisé de Proxmox<br>avec GPU passthrough sur baremetal</div>
    <div class="tagline">Une journée pour maîtriser le déploiement de Proxmox VE avec<br>GPU PCI passthrough sur infrastructure OVHcloud baremetal</div>
    <div class="brand">PSMC OVHcloud</div>
</div>

<!-- PAGE 2: INTRODUCTION & VALUE PROPOSITION -->
<div class="page">
    <h2>Accélérez vos workloads GPU en virtualisation</h2>
    <p class="intro-text">
        Découvrez comment déployer Proxmox VE sur une infrastructure baremetal OVHcloud
        et configurer le GPU PCI passthrough pour vos machines virtuelles.
        Notre programme immersif vous permet de pratiquer dans un environnement réel,
        sécurisé et accompagné — de la théorie à la maîtrise opérationnelle en une seule journée.
    </p>

    <h3>Ce que vous allez accomplir</h3>
    <ul class="benefits">
        <li>Maîtriser le déploiement automatisé de Proxmox VE sur baremetal</li>
        <li>Configurer IOMMU et VFIO pour l'isolation GPU complète</li>
        <li>Créer des VMs avec accès GPU direct (passthrough PCIe)</li>
        <li>Valider le bon fonctionnement du GPU dans les machines virtuelles</li>
        <li>Appliquer les bonnes pratiques de sécurité et de performance</li>
    </ul>

    <div class="highlight-box">
        <h4>⏱ Format optimisé : 1 journée</h4>
        <p style="margin:0; font-size: 14px; color: #555;">
            Un programme intensif mais progressif, conçu pour vous rendre opérationnel
            rapidement sur le GPU passthrough avec Proxmox VE.
        </p>
    </div>
</div>

<!-- PAGE 3: PROGRAMME & TIMELINE -->
<div class="page">
    <h2>Un parcours structuré et progressif</h2>

    <div class="timeline">
        <div class="timeline-item">
            <div class="timeline-badge">1</div>
            <div class="timeline-content">
                <h4>Prérequis et Concepts — ~1h</h4>
                <p>Mise en place de votre environnement, présentation de l'architecture Proxmox VE, PCI passthrough et IOMMU.</p>
            </div>
        </div>
        <div class="timeline-item">
            <div class="timeline-badge">2</div>
            <div class="timeline-content">
                <h4>Provisionnement Baremetal — ~1h</h4>
                <p>Création d'instances GPU sur OVHcloud OpenStack, configuration SSH et authentification.</p>
            </div>
        </div>
        <div class="timeline-item">
            <div class="timeline-badge">3</div>
            <div class="timeline-content">
                <h4>Installation Proxmox & GPU Config — ~2 à 3h</h4>
                <p>Installation automatisée de Proxmox VE, configuration IOMMU, blacklist drivers, liaison VFIO-PCI.</p>
            </div>
        </div>
        <div class="timeline-item">
            <div class="timeline-badge">4</div>
            <div class="timeline-content">
                <h4>Création VM & Validation — ~1h</h4>
                <p>Création de VMs Q35/OVMF avec hostpci GPU, validation nvidia-smi, tests CUDA.</p>
            </div>
        </div>
    </div>

    <h3>Votre environnement de formation</h3>
    <div class="env-cards">
        <div class="env-card">
            <h4>🌐 SkillHub</h4>
            <ul>
                <li>Interface web interactive</li>
                <li>Contenu multilingue (FR/EN)</li>
                <li>Modules pédagogiques structurés</li>
                <li>Suivi de progression</li>
            </ul>
        </div>
        <div class="env-card">
            <h4>🔬 Labs</h4>
            <ul>
                <li>Instance baremetal GPU réelle</li>
                <li>Automatisation CLI complète</li>
                <li>Proxmox VE avec GPU passthrough</li>
                <li>Validation automatisée</li>
            </ul>
        </div>
    </div>
</div>

<!-- PAGE 4: MODULES -->
<div class="page">
    <h2>6 modules pour une maîtrise complète</h2>
    <p class="intro-text">Chaque module est conçu pour vous faire progresser étape par étape, du provisionnement baremetal à la validation GPU dans les VMs.</p>

    <div class="modules-grid">
        <div class="module-card">
            <div class="module-number">1</div>
            <h4>Concepts Fondamentaux</h4>
            <p>Proxmox VE, KVM, IOMMU, VFIO et PCI passthrough</p>
        </div>
        <div class="module-card">
            <div class="module-number">2</div>
            <h4>Provisionnement</h4>
            <p>Création d'instances baremetal GPU sur OpenStack</p>
        </div>
        <div class="module-card">
            <div class="module-number">3</div>
            <h4>Installation Proxmox</h4>
            <p>Déploiement automatisé sur Debian 12</p>
        </div>
        <div class="module-card">
            <div class="module-number">4</div>
            <h4>GPU Passthrough</h4>
            <p>IOMMU, VFIO, blacklist et isolation</p>
        </div>
        <div class="module-card">
            <div class="module-number">5</div>
            <h4>Création de VMs</h4>
            <p>Q35, OVMF, hostpci et drivers GPU</p>
        </div>
        <div class="module-card">
            <div class="module-number">6</div>
            <h4>Validation</h4>
            <p>nvidia-smi, CUDA et benchmarks</p>
        </div>
    </div>

    <h3>À qui s'adresse ce programme ?</h3>
    <div class="features">
        <div class="feature-card">
            <h4>👨‍💻 Administrateurs Système</h4>
            <p>Vous gérez des infrastructures et souhaitez maîtriser le GPU passthrough sur Proxmox.</p>
        </div>
        <div class="feature-card">
            <h4>🚀 Ingénieurs DevOps & Cloud</h4>
            <p>Vous automatisez des déploiements et avez besoin de GPU en virtualisation.</p>
        </div>
        <div class="feature-card">
            <h4>🧠 Data Scientists & ML Engineers</h4>
            <p>Vous avez besoin d'accès GPU performant dans des environnements virtualisés.</p>
        </div>
        <div class="feature-card">
            <h4>📊 Architectes Infrastructure</h4>
            <p>Vous concevez des plateformes GPU-as-a-Service sur infrastructure privée.</p>
        </div>
    </div>
</div>

<!-- PAGE 5: RESULTS & CTA -->
<div class="page">
    <h2>Vos acquis à l'issue de la formation</h2>

    <ul class="benefits">
        <li>Compréhension complète de l'architecture PCI passthrough et IOMMU</li>
        <li>Autonomie dans le déploiement de Proxmox VE sur baremetal</li>
        <li>Maîtrise de la configuration VFIO et de l'isolation GPU</li>
        <li>Capacité à créer des VMs optimisées pour les workloads GPU</li>
        <li>Connaissance des outils de validation et de troubleshooting</li>
        <li>Automatisation complète via CLI Python</li>
    </ul>

    <div class="highlight-box">
        <h4>🎯 Prérequis simples</h4>
        <p style="margin:0; font-size: 14px; color: #555;">
            Connaissance de base de Linux et de la ligne de commande,
            Python 3.9+ installé, et un projet OVHcloud Public Cloud avec accès baremetal GPU.
            Nous fournissons tout le reste.
        </p>
    </div>

    <div class="cta">
        <h3>Prêt à démarrer ?</h3>
        <p>Contactez notre équipe pour planifier votre session de formation GPU Passthrough sur Proxmox.</p>
        <div class="contact">psmc@ovhcloud.com</div>
    </div>

    <div class="footer">
        <p>© PSMC OVHcloud — Programme OPCP Proxmox GPU Passthrough</p>
    </div>
</div>

</body>
</html>
"""

output_path = "docs/OPCP-Proxmox-GPU-Passthrough-Marketing.pdf"
HTML(string=html_content).write_pdf(output_path)
print(f"PDF generated: {output_path}")
