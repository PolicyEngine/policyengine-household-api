# CI/CD Pipeline Implementation

This folder contains the implementation of a comprehensive CI/CD pipeline for the PolicyEngine Household API using GitHub Actions, Docker, and Google Cloud App Engine.

## Overview

The pipeline implements the following stages:
1. **Build & Test** - Code compilation, dependency installation, and test execution
2. **Security Scanning** - Static analysis and dependency vulnerability scanning
3. **Docker Build** - Multi-stage Docker image creation and optimization
4. **Deployment** - Automated deployment to Google Cloud App Engine
5. **Verification** - Health checks and smoke tests
6. **Cleanup** - Automatic cleanup of old App Engine versions

## Files Structure

```
under_development/
├── .github/
│   └── workflows/
│       ├── ci.yml                 # CI workflow for PRs and development
│       └── deploy-production.yml  # Production deployment workflow
├── Dockerfile.production          # Production-optimized Dockerfile
├── .dockerignore                  # Docker build context exclusions
├── (uses existing gcp/policyengine_household_api/app.yaml)
├── requirements.txt               # Python dependencies
└── README.md                      # This file
```

## Key Features

### Production Dockerfile
- **Multi-stage build** for optimized image size
- **Security hardening** with non-root user
- **Health checks** for container monitoring
- **No Redis dependency** (removed as requested)
- **Optimized layers** for faster builds
- **Compatible with existing GCP configuration**

### GitHub Actions Workflows

#### CI Workflow (`ci.yml`)
- Triggers on PRs and development branches
- Runs tests, linting, and security scans
- Tests Docker build without pushing
- Code quality checks (mypy, pylint)

#### Production Deployment (`deploy-production.yml`)
- Triggers on main branch pushes
- Full CI/CD pipeline execution
- Automated deployment to App Engine
- Traffic management and version cleanup

### App Engine Configuration
- **Uses existing configuration** from `gcp/policyengine_household_api/app.yaml`
- **Custom runtime** with Docker
- **Automatic scaling** (1-1 instances as configured)
- **Health checks** for liveness and readiness
- **Resource optimization** (8GB RAM, 2 CPU as configured)

## Setup Requirements

### GitHub Secrets
Your project already has the required secrets configured:
- `GCP_SA_KEY` - Already configured for existing deployment workflow
- All other required environment variables are already set up

### Google Cloud Setup
Your project already has Google Cloud fully configured:
- **Service Account**: `github-deployment@policyengine-household-api.iam.gserviceaccount.com`
- **APIs**: Already enabled and configured
- **App Engine**: Already created and configured
- **Authentication**: Integrated with existing GitHub Actions workflow

## Usage

### Development Workflow
1. Create feature branch from `develop`
2. Make changes and push
3. CI workflow runs automatically
4. Create PR to `develop` or `main`

### Production Deployment
1. Merge to `main` branch
2. Production deployment starts automatically
3. Monitor deployment in GitHub Actions
4. Verify application health

### Manual Deployment
Use the workflow dispatch trigger:
1. Go to Actions → Deploy to Production
2. Click "Run workflow"
3. Select environment and run

## Monitoring

### Health Endpoints
- **Liveness**: `/liveness_check` - Container health check
- **Readiness**: `/readiness_check` - App startup readiness

### App Engine Monitoring
- **Versions**: Track deployment versions
- **Logs**: Cloud Logging integration
- **Metrics**: Performance and scaling metrics

## Security Features

- **Non-root container user**
- **Static code analysis**
- **Secrets management via GitHub**
- **IAM principle of least privilege**

## Cost Optimization

- **Automatic scaling** based on demand
- **Version cleanup** (keeps last 5 versions)
- **Resource limits** (4GB RAM, 2 CPU)
- **Efficient Docker layers**

## Troubleshooting

### Common Issues

1. **Build Failures**:
   - Check Docker build logs
   - Verify requirements.txt dependencies
   - Check .dockerignore exclusions

2. **Deployment Failures**:
   - Verify GCP credentials
   - Check App Engine quotas
   - Review app.yaml configuration

3. **Health Check Failures**:
   - Verify health endpoint implementation
   - Check application startup logs
   - Review readiness check configuration

### Debug Commands

```bash
# Check App Engine versions
gcloud app versions list

# View application logs
gcloud app logs tail

# Check service status
gcloud app describe
```

## Next Steps

1. **Implement health endpoints** in your API
2. **Configure monitoring alerts**
3. **Set up staging environment**
4. **Add database migration handling**
5. **Implement blue-green deployments**

## Support

For issues or questions:
1. Check GitHub Actions logs
2. Review App Engine logs
3. Verify GCP project configuration
4. Check service account permissions
