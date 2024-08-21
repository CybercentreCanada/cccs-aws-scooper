# AWS Scooper

(La version française suit)

- [AWS Scooper](#aws-scooper)
  - [Licence](#licence)
  - [Description](#description)
    - [Supported Logging Services](#supported-logging-services)
  - [Prerequisites](#prerequisites)
  - [Installation Instructions](#installation-instructions)
  - [Updates](#updates)
  - [Agent Management](#agent-management)
    - [Deployment and Usage](#deployment-and-usage)
      - [CLI Options](#cli-options)
  - [Development and Testing](#development-and-testing)
  - [Contributions](#contributions)
    - [Pull Request Guidelines](#pull-request-guidelines)
  - [Cost](#cost)

## Licence

The resources contained herein are © His Majesty in Right of Canada as Represented by the Minister of National Defence.

**FOR OFFICIAL USE** All Rights Reserved. All intellectual property rights subsisting in the resources contained herein are,
and remain the property of the Government of Canada. No part of the resources contained herein may be reproduced or disseminated
(including by transmission, publication, modification, storage, or otherwise), in any form or any means, without the written
permission of the Communications Security Establishment (CSE), except in accordance with the provisions of the *Copyright Act*, such
as fair dealing for the purpose of research, private study, education, parody or satire. Applications for such permission shall be
made to CSE.

**The resources contained herein are provided “as is”, without warranty or representation of any kind by CSE, whether express or**
**implied, including but not limited to the warranties of merchantability, fitness for a particular purpose and noninfringement.**
**In no event shall CSE be liable for any loss, liability, damage or cost that may be suffered or incurred at any time arising**
**from the provision of the resources contained herein including, but not limited to, loss of data or interruption of business.**

CSE is under no obligation to provide support to recipients of the resources contained herein.

This licence is governed by the laws of the province of Ontario and the applicable laws of Canada. Legal proceedings related to
this licence may only be brought in the courts of Ontario or the Federal Court of Canada.

**Notwithstanding the foregoing, third party components included herein are subject to the ownership and licensing provisions**
**noted in the files associated with those components.**

## Description

This project is designed to be run by admins to gather data about their AWS environment. Its main purpose is for data collection and aggregation of core AWS workloads in a given AWS account or organization. The collected logging reports are centralized to an S3 bucket or can be written locally as JSON files. The S3 bucket's name will be randomly generated and will contain `scooper` as part of its name. Repeated Scooper deployments will update the S3 bucket with new logging reports.

### Supported Logging Services

| Logging Service     | Status              |
| ------------------- | ------------------- |
| CloudTrail Logs     | Fully Supported     |
| Config Logs         | Fully Supported     |
| CloudWatch Logs     | Reports Only        |

## Prerequisites

- [Python 3.9+](https://www.python.org/downloads/)
- [Node.js 14.15+](https://nodejs.org/en/download)
- [AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html#getting_started_install)
- [Bootstrapped account](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html#getting_started_bootstrap)

## Installation Instructions

- Clone repository:
  - `git clone https://github.com/CybercentreCanada/cccs-aws-scooper.git`
- Change your current directory to the project directory:
  - `cd cccs-aws-scooper`
- Install necessary dependencies:
  - `python3 -m venv .venv && source .venv/bin/activate && pip install -r scooper/requirements.txt`

## Updates

To update the project to the latest version, follow these steps:
- Check the GitHub repository for any new releases or updates.
- If an updated version is available, run `git pull` and re-run Scooper.
Users can also [watch the repository](https://docs.github.com/en/account-and-profile/managing-subscriptions-and-notifications-on-github/setting-up-notifications/configuring-notifications#configuring-your-watch-settings-for-an-individual-repository) to receive notifications about the latest updates.

## Agent Management

### Deployment and Usage

Scooper can be run using any AWS principal that has been assigned an [AdministratorAccess](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AdministratorAccess.html) policy, but organizational level deployment must be run within the AWS management/root account.

After pulling the repository to your environment and installing the required dependencies, users must have valid credentials configured to their AWS account of choice.

Run `python -m scooper --help` to see all CLI options.

#### CLI Options

Scooper can be run with the following options:
- `--cloudtrail-scoop`
  - Whether to perform historical CloudTrail data collection of current account and region. Aggregates CloudTrail events by hour and writes to S3 of your choice.
- `--configure-logging`
  - Spin-up CloudFormation stack based on existing logging within environment in current region.
- `--destroy`
  - Used to destroy all CloudFormation resources created by Scooper in the current region.
  - Users managing Scooper deployments across multiple regions must switch to each region to delete the associated resources.
- `--level [account|org]`
  - Which level of enumeration to perform: `account` or `org`.
  - Choose between Account Enumeration and Organization Enumeration. if `org` is specified then `--role-name` must also be specified.
  - The default level is set to `account`.
- `--lifecycle-rules TEXT`
  - Used to specify the S3 storage class, and duration of lifecycle policy for the Scooper S3 bucket.
  - Formatted as follows: `STORAGE_CLASS(xd),EXPIRY(yd)`
    - `x` represents the number of days before an object is transitioned to a given `STORAGE_CLASS`.
    - `y` represents the number of days before an object is expired/deleted (must be greater than x).
  - Omitting lifecycle rules on subsequent deployments with `configure-logging` will remove the lifecycle rules in place on the created S3 bucket.
  - Supported storage classes can be found using the `python -m scooper configure-logging --help` command.
  - Omitting the `--lifecycle-rules` option results in using the default storage class of `STANDARD` and no lifecycle policy will be in place on the created S3 bucket.
  - Examples:
    - `--lifecycle-rules "GLACIER(1d),EXPIRY(12d)"`
     - Objects will move to GLACIER after 1 day, and expire after 12 days.
    - `--lifecycle-rules "GLACIER(1d)"`
     - Objects will move to GLACIER after 1 day, with no expiry.
    - `--lifecycle-rules "EXPIRY(5d)"`
     - Objects are stored in STANDARD and expire after 5 days.
    - `--lifecycle-rules "INTELLIGENT_TIERING(1d),DEEP_ARCHIVE(10d),EXPIRY(12d)"`
     - Objects will move to INTELLIGENT_TIERING after 1 day, DEEP_ARCHIVE after 10 days, and expire after 12 days.
  - Unsupported lifecycle transitions can be found [here](https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-transition-general-considerations.html).
- `--role-name TEXT`
  - Name of role with organizational account access.
  - If Organization level enumeration is chosen, the name of the role with organizational account access must be specified.
  - The default name is set to `OrganizationAccountAccessRole` for users using AWS Organizations for account management, and will differ for other account factory tools.

## Development and Testing

1. Pull down the repo from GitHub and start a new virtual environment on your system.
   - For Linux-based systems: `python3 venv .venv && source .venv/bin/activate`.
2. In the virtual environment, run `pip install -r requirements-dev.txt`.
3. Run `pre-commit install` to install the git pre-commit hooks.

To run unit tests across our modules from the root directory run `pytest`.
To test the enumeration of the different log sources, the following commands can be run:

- `pytest scooper/cdk/tests/unit/test_config.py`
  - Tests Config Logs
- `pytest scooper/cdk/tests/unit/test_cloudtrail.py`
  - Tests CloudTrail Logs

## Contributions

### Pull Request Guidelines

Pull requests are only possible for authorized contributors to the repository. Interested parties may contact the repository owners to seek permission to become an authorized contributor, and must adhere to the following guidelines when submitting pull requests:

- Pull requests should primarily focus on adding new features, fixing bugs, or improving existing functionality.
- Forking of the repository is NOT allowed.
- New branches can only be created by authorized contributors to the project.
- Only project contributors will have access to modify the main branch.
- All PRs must be supported by documentation explaining the purpose of the change (bug fix, new feature, etc)
- If possible, tests should be added to cover any changes made to ensure proper functionality.
- Any new or modified code must pass linting, formatting, and security audits.

## Cost

The usage of Scooper will incur costs associated with logging and storage resources created by Scooper's CloudFormation stack. Account and/or organization owners are solely responsible for any costs incurred as the result of using Scooper or any derivative of it.

# AWS Scooper FR

- [AWS Scooper FR](#aws-scooper-fr)
  - [Licence FR](#licence-fr)
  - [Description FR](#description-fr)
    - [Services de Journalisation Soutenus](#services-de-journalisation-soutenus)
  - [Prérequis](#prérequis)
  - [Instructions d'installation](#instructions-dinstallation)
  - [Mises à jour](#mises-à-jour)
  - [Gestion des agents](#gestion-des-agents)
    - [Déploiement et Usage](#déploiement-et-usage)
      - [Options CLI](#options-cli)
  - [Essais et Développement](#essais-et-développement)
  - [Contributions FR](#contributions-fr)
    - [Directives des demandes de tirage](#directives-des-demandes-de-tirage)
  - [Coût](#coût)

## Licence FR

Les ressources contenues aux présentes sont © Sa Majesté le Roi du chef du Canada, représenté par le ministre de la Défense nationale.

**RÉSERVÉ À DES FINS OFFICIELLES** Tous droits réservés. Tous les droits de propriété intellectuelle
relatifs aux ressources contenues aux présentes sont et demeurent la propriété du gouvernement du
Canada. Aucune partie des ressources contenues aux présentes ne peut être reproduite ou diffusée (y
compris par transmission, publication, modification, stockage, ou autrement), sous quelque forme ou par
quelque moyen que ce soit, sans l’autorisation écrite du Centre de la sécurité des télécommunications
(CST), sauf conformément aux dispositions de la *Loi sur le droit d’auteur*, comme celles portant sur
l’utilisation équitable aux fins de recherche, d’étude privée, d’éducation, de parodie ou de satire.
Toute demande d’autorisation doit être présentée au CST.

**Les ressources contenues aux présentes sont fournies « telles quelles », sans garantie ni**
**représentation de quelque nature que ce soit par le CST, expresses ou implicites, y compris, sans**
**s’y limiter, les garanties de qualité marchande, d’adaptation à un usage particulier et d’absence de**
**contrefaçon. En aucun cas, le CST ne saurait être tenu responsable des pertes, des inconvénients,**
**des dommages ou des coûts encourus suivant la fourniture des ressources contenues dans la présente,**
**y compris, sans toutefois s’y limiter, les pertes de données ou l’interruption des activités.**


Le CST n’est pas tenu de fournir de l’aide aux destinataires des ressources contenues aux présentes.

La présente licence est régie par les lois de la province de l’Ontario et les lois applicables du
Canada. Les procédures judiciaires liées à la présente licence ne peuvent être intentées que devant les
tribunaux de la province de l’Ontario ou portées devant la Cour fédérale du Canada.

**Nonobstant ce qui précède, les composants tiers compris aux présentes sont soumis aux dispositions**
**relatives à la propriété et aux licences notées dans les dossiers associés à ces composants.**

## Description FR

Ce projet est désigné d'être exécuté par des administrateurs pour rassembler des données sur leur environnement AWS. Il sert principalement à la collecte et à l'agrégation de données sur les charges de travail AWS dans un compte ou une organisation AWS. Les rapports de journalisation collectés sont centralisés dans un compartiment S3 ou peuvent être écrits localement sous forme JSON. Le nom du compartiment S3 sera généré au hasard et contiendra `scooper` dans son nom. Les déploiements Scooper répétés mettront à jour le compartiment S3 avec de nouveaux rapports de journalisation.

### Services de Journalisation Soutenus

| Services de Journalisation     | Statut           |
| -------------------    | ------------------- |
| Journaux CloudTrail    | Soutenu Entièrement      |
| Journaux Config        | Soutenu Entièrement      |
| Journaux CloudWatch    | Rapports seulement       |

## Prérequis

- [Python 3.10+](https://www.python.org/downloads/)
- [Node.js 14.15+](https://nodejs.org/en/download)
- [AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html#getting_started_install)
- [Bootstrap votre compte](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html#getting_started_bootstrap)

## Instructions d'installation

- Clonez le dépôt:
  - `git clone https://github.com/CybercentreCanada/cccs-aws-scooper.git`
- Changez votre répertoire actuel vers le répertoire du projet:
  - `cd cccs-aws-scooper`
- Installer les dépendances requises:
  - `python3 -m venv .venv && source .venv/bin/activate && pip install -r scooper/requirements.txt`

## Mises à jour

Pour mettre à jour le projet vers la dernière version :
- Vérifier le dépôt pour toute nouvelle version ou mise à jour
- Si une version mise à jour est disponible, lancez `git pull` et exécutez à nouveau Scooper.
- Les usagers peuvent [surveiller un dépôt](https://docs.github.com/fr/account-and-profile/managing-subscriptions-and-notifications-on-github/setting-up-notifications/configuring-notifications#configuring-your-watch-settings-for-an-individual-repository) pour recevoir des notifications sur les dernières mises à jour.

## Gestion des agents

### Déploiement et Usage

Scooper peut être exécutée par n'importe quel principal AWS qui a été attribué une politique [AdministratorAccess](https://docs.aws.amazon.com/fr_fr/aws-managed-policy/latest/reference/AdministratorAccess.html), mais le développement au niveau organisationnel doit être exécuté dans le compte AWS Management.

Après avoir récupéré le dépôt dans votre environnement et installé les dépendances requises, les usagers doivent disposer d'informations d'identification valides configurées sur le compte AWS de leur choix.

Lancez `python -m scooper --help` pour voir toutes les options CLI.

#### Options CLI

Scooper peut être exécuté avec les options suivantes :
- `--cloudtrail-scoop`
  - Utilisé pour exécuter la collecte des données CloudTrail historiques sur le compte courant et la région actuelle. Agrège des CloudTrail événements par heure et les écrit au compartiment S3 de votre choix.
- `--configure-logging`
  - Utilisé pour créer une pile CloudFormation basée sur la journalisation existante dans l'environnement de la région actuelle.
- `--destroy`
  - Utilisé pour détruire toutes les ressources CloudFormation créées par Scooper dans la région actuelle.
  - Les utilisateurs qui gèrent des déploiements Scooper dans plusieurs régions doivent supprimer les ressources associées dans chaque région.
- `--level [account|org]`
  - Le niveau d'énumération à effectuer :  `account` ou `org`.
  - Choisissez entre l'énumération de compte et l'énumération d'organisation. Si `org` est spécifié, `--role-name` doit également être spécifié.
  - Le niveau par défaut est `account`.
- `--lifecycle-rules TEXT`
  - Utilisé pour spécifier la classe de stockage S3 et la durée de la politique du cycle de vie pour le compartiment S3 Scooper.
  - Formaté comme suit : `STORAGE_CLASS(xd),EXPIRY(yd)`
    - `x` représente le nombre de jours avant qu'un objet ne soit transféré vers une `STORAGE_CLASS` donnée.
    - `y` représente le nombre de jours avant qu'un objet soit expiré/supprimé (doit être supérieur à x).
  - Omettre les règles de cycle de vie sur les déploiements ultérieurs avec `configure-logging` supprimera les règles de cycle de vie existantes en place sur le compartiment S3 créé.
  - Omettre l'option `--lifecycle-rules` entraîne l'utilisation de la classe de stockage par défaut de `STANDARD` et aucune politique de cycle de vie ne sera en place sur le bucket S3 créé.
  - Exemples :
    - `--lifecycle-rules "GLACIER(1d),EXPIRY(12d)"`
     - Les objets seront déplacés vers GLACIER après 1 jour, et expireront après 12 jours.
    - `--lifecycle-rules "GLACIER(1d)"`
     - Les objets seront déplacés vers GLACIER après 1 jour, sans expiration.
    - `--lifecycle-rules  "EXPIRY(5d)"`
     - Les objets sont stockés dans STANDARD et expirent après 5 jours.
    - `--lifecycle-rules "INTELLIGENT_TIERING(1d),DEEP_ARCHIVE(10d),EXPIRY(12d)"`
     - Les objets seront déplacés vers INTELLIGENT_TIERING après 1 jour, vers DEEP_ARCHIVE après 10 jours et expireront après 12 jours.
  - Les transitions du cycle de vie non prises en charge peuvent être trouvées [ici](https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-transition-general-considerations.html).
- `--role-name TEXT`
  - Nom du rôle avec accès au compte d'organisation.
  - Si l'énumération au niveau de l'organisation est choisie, le nom du rôle avec accès au compte de l'organisation doit être spécifié.
  - Le nom par défaut est `OrganizationAccountAccessRole` pour les usagers qui utilisent AWS Organizations pour la gestion des comptes, et sera différent pour les autres outils de création de comptes.

## Essais et Développement

1. Récupérez le dépôt de GitHub et démarrez un nouvel environnement virtuel sur votre système.
   - Pour les systèmes Linux : `python3 venv .venv && source .venv/bin/activate`.
2. Dans l'environnement virtuel, lancez `pip install -r requirements-dev.txt`.
3. Exécutez `pre-commit install` pour installer les crochets de pré-commit de git.

Pour exécuter les tests unitaires de nos modules à partir du répertoire racine, exécutez `pytest`.
Pour tester l'énumération des différentes sources de journaux, les commandes suivantes peuvent être exécutées :

- `pytest scooper/cdk/tests/unit/test_config.py`
  - Tests des journaux Config
- `pytest scooper/cdk/tests/unit/test_cloudtrail.py`
  - Tests des journaux CloudTrail

## Contributions FR

### Directives des demandes de tirage

Les demandes de tirage (pull requests) sont disponibles seulement pour les contributeurs autorisés du dépôt. Les parties intéressées peuvent contacter les propriétaires du dépôt pour demander la permission de devenir un contributeur autorisé, et doivent adhérer aux directives suivantes lorsqu'elles soumettent des demandes de tirage:

- Les demandes de tirage doivent se concentrer principalement sur l'ajout de nouvelles fonctionnalités, la correction de bogues ou l'amélioration de fonctionnalités existantes.
- La duplication d'un dépôt est INTERDITE.
- Les nouvelles branches peuvent être créées seulement par des contributeurs autorisés.
- Seuls les contributeurs au projet auront accès à la modification de la branche principale.
- Toutes les demandes de tirage doivent être accompagnés d'une documentation expliquant le but du changement (correction de bogues, nouvelle fonctionnalité, etc.).
- Si possible, des tests doivent être ajoutés pour couvrir tous les changements effectués afin de garantir une fonctionnalité correcte.
- Tout code nouveau ou modifié doit passer les audits de lint, de formatage et de sécurité.

## Coût

L'utilisation de Scooper entraînera des coûts liés à la journalisation et aux ressources de stockage créées par la pile CloudFormation de Scooper. Les propriétaires de comptes et/ou d'organisations sont responsables des coûts encourus du fait de l'utilisation de Scooper ou d'un de ses dérivés.
