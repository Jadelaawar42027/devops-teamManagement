# One-time Azure and GitHub setup

Everything in Azure is created by Terraform (`infra/terraform/`) from the CD pipeline, except
the two things Terraform needs before it can run:

1. **A place to keep its state**: a storage account plus a blob container, in the class resource group.
2. **Credentials**: the class service principal, plus the passwords and settings stored as GitHub secrets and variables.

Do this once, from your own machine, signed in with your IE account (Contributor on the class
resource group). After this, nothing is created or changed by hand: every merge to `main` runs CD.

## 0. Values used below

```bash
RG=rg-sdd-3a                      # TODO: your class's resource group (rg-sdd-3a or rg-sdd-3b)
LOCATION=westeurope
STATE_ACCOUNT=jelaawarieu2023tfstate   # 3-24 lowercase letters/digits, globally unique
STATE_CONTAINER=tfstate
```

## 1. Sign in and check the resource group

```bash
az login
az account show --query "{subscription:id, tenant:tenantId}" -o table
az group show --name "$RG" --query "{name:name, location:location}" -o table
```

The service principal cannot register resource providers (it is Contributor on one resource
group only), so check that these are already `Registered` on the subscription. If one is not,
ask the professor:

```bash
for p in Microsoft.Network Microsoft.Compute Microsoft.Sql Microsoft.Storage; do
  echo "$p $(az provider show --namespace $p --query registrationState -o tsv)"
done
```

## 2. Storage for the Terraform state

```bash
az storage account create --name "$STATE_ACCOUNT" --resource-group "$RG" --location "$LOCATION" \
  --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 \
  --allow-blob-public-access false

# keep old versions of the state file, so a broken state can be rolled back
az storage account blob-service-properties update --account-name "$STATE_ACCOUNT" \
  --resource-group "$RG" --enable-versioning true

# --auth-mode key: Contributor may read the account keys (listKeys), but has no blob data role
az storage container create --name "$STATE_CONTAINER" --account-name "$STATE_ACCOUNT" --auth-mode key
```

The state file is in this container under the key `jelaawar-ieu2023.tfstate`. It holds the SQL
admin password in plain text, which is why it lives here and never on disk or in git. The
`azurerm` backend locks it with a blob lease, so two runs can never apply at the same time.

## 3. The service principal and the role it needs

The professor provides the class service principal. It needs exactly one role:
**Contributor, scoped to the class resource group**. That is enough to:

- create and change every resource in `infra/terraform/` (network, VM, load balancer, DNS zone, SQL server and databases),
- read the state storage account's keys (`listKeys`), which the Terraform backend uses,
- run `az vm run-command invoke` on the VM (the deploy step), and
- add and remove the temporary SQL firewall rule for the pipeline runner.

It needs no role assignments of its own, and it does not need to create resource groups. On a
personal subscription you would make the equivalent yourself:

```bash
az ad sp create-for-rbac --name jelaawar-ieu2023-cd --role Contributor \
  --scopes "/subscriptions/<subscription-id>/resourceGroups/$RG"
```

Keep its secret only in GitHub secrets. If it is ever pushed to the repository, it is
compromised: report it to the professor (class SP) and follow the leaked-secret steps in the README.

## 4. SSH key for the VM

```bash
ssh-keygen -t ed25519 -f ~/.ssh/jelaawar-azure -C "jelaawar-ieu2023 vm"
```

The public half (`~/.ssh/jelaawar-azure.pub`) goes into the variable `VM_SSH_PUBLIC_KEY`. The
private half never leaves your laptop.

## 5. GitHub secrets and variables

`gh secret set NAME` prompts for the value, so it is never in a file or your shell history.
Run these from the repository folder.

```bash
# the class service principal (values from the professor)
gh secret set AZURE_CLIENT_ID
gh secret set AZURE_CLIENT_SECRET
gh secret set AZURE_TENANT_ID
gh secret set AZURE_SUBSCRIPTION_ID

# where the Terraform state lives (from step 2)
gh secret set TF_STATE_RESOURCE_GROUP --body "$RG"
gh secret set TF_STATE_STORAGE_ACCOUNT --body "$STATE_ACCOUNT"
gh secret set TF_STATE_CONTAINER --body "$STATE_CONTAINER"

# generated passwords: random, with the upper/lower/digit/symbol mix Azure SQL requires.
# If you want to query the databases yourself later, save the admin password in your password
# manager before setting it.
gh secret set SQL_ADMIN_PASSWORD --body "$(openssl rand -base64 24 | tr -d '/+=')Aa1-"
gh secret set KPI_DB_PASSWORD --body "$(openssl rand -base64 24 | tr -d '/+=')Aa1-"
gh secret set ROUTING_DB_PASSWORD --body "$(openssl rand -base64 24 | tr -d '/+=')Aa1-"

# the only address allowed to SSH in (through the load balancer, port 50022)
gh secret set ADMIN_CIDR --body "$(curl -s https://api.ipify.org)/32"

# not secret
gh variable set AZURE_RESOURCE_GROUP --body "$RG"
gh variable set VM_SSH_PUBLIC_KEY < ~/.ssh/jelaawar-azure.pub
gh variable set SEED_DEMO --body 1    # optional; 1 is the default
```

## 6. First deploy

Merge a pull request into `main`. CI runs, and when it passes CD:

1. pushes `ghcr.io/<owner>/kpi:<sha>` and `ghcr.io/<owner>/routing:<sha>`,
2. runs `terraform apply`. The first apply takes about 10 minutes, mostly the SQL server and the VM,
3. creates the contained users `kpi_svc` and `routing_svc`,
4. waits for cloud-init to finish installing Docker on the new VM, then starts the stack,
5. polls `http://jelaawar-ieu2023.westeurope.cloudapp.azure.com/health` until it returns 200 with the new SHA.

## 7. Checking what was created

```bash
az resource list --resource-group "$RG" --query "[?starts_with(name, 'jelaawar-ieu2023')].{name:name, type:type}" -o table

# The DNS zone is not delegated (no owned domain), so ask its own name server directly:
NS=$(az network dns zone show -g "$RG" -n jelaawar-ieu2023.devops.ie --query "nameServers[0]" -o tsv)
nslookup app.jelaawar-ieu2023.devops.ie "$NS"

# SSH, only from ADMIN_CIDR:
ssh -i ~/.ssh/jelaawar-azure -p 50022 azureuser@jelaawar-ieu2023.westeurope.cloudapp.azure.com
sudo docker compose -f /opt/app/deploy/docker-compose.prod.yml logs --tail 50
```

## Running Terraform from your laptop (rarely needed)

```bash
cd infra/terraform
export ARM_SUBSCRIPTION_ID=$(az account show --query id -o tsv)   # your az login is used
export TF_VAR_sql_admin_password='...'                            # the same value as the secret
cp terraform.tfvars.example terraform.tfvars                      # git-ignored; fill it in
terraform init -backend-config="resource_group_name=$RG" -backend-config="storage_account_name=$STATE_ACCOUNT" \
  -backend-config="container_name=$STATE_CONTAINER" -backend-config="key=jelaawar-ieu2023.tfstate"
terraform plan
```

If the admin password here differs from the GitHub secret, the next CD run sets it back.

To remove everything when grades are published: `terraform destroy` with the same init, then
delete the state storage account.
