# HACS Repository Setup Guide

This guide helps resolve HACS validation issues for the Tibber Unofficial integration.

## Current Validation Issues

### 1. Repository Issues Not Enabled
**Error**: `The repository does not have issues enabled`
**Fix**: Enable GitHub Issues in repository settings

### 2. Missing Repository Topics
**Error**: `The repository has no valid topics`
**Fix**: Add required topics to repository

## Step-by-Step Resolution

### Enable GitHub Issues

1. Go to your GitHub repository: `https://github.com/senaxx/Tibber_unofficial`
2. Click on **Settings** tab
3. Scroll down to **Features** section
4. Check the box next to **Issues** to enable it
5. Click **Save** if prompted

### Add Required Topics

1. On your repository main page, click the ⚙️ (gear) icon next to **About**
2. In the **Topics** field, add these topics (separated by spaces):
   ```
   home-assistant hacs integration tibber energy smart-home grid-rewards homevolt electric-vehicle
   ```
3. Click **Save changes**

### Recommended Topics for HACS

For Home Assistant integrations, these topics are commonly used:

**Required/Recommended:**
- `home-assistant` - Identifies as Home Assistant related
- `hacs` - Indicates HACS compatibility
- `integration` - Specifies it's an integration
- `custom-component` - Alternative to integration

**Domain-Specific:**
- `tibber` - The service provider
- `energy` - Energy domain
- `smart-home` - General smart home category
- `grid-rewards` - Specific feature
- `homevolt` - Tibber battery system
- `electric-vehicle` - EV charging rewards

**Quality Indicators:**
- `gold-standard` - Indicates Gold quality
- `production-ready` - Indicates stability
- `diagnostics` - Advanced features
- `repair-flows` - Modern HA features

### Final Topics Recommendation

```
home-assistant hacs integration tibber energy smart-home grid-rewards homevolt electric-vehicle gold-standard
```

## Verification

After making these changes:

1. Wait 5-10 minutes for GitHub to update
2. Re-run HACS validation: https://hacs.xyz/docs/publish/action/
3. Both issues should be resolved

## Additional HACS Requirements Checklist

✅ **Repository Structure**
- [x] `custom_components/tibber_unofficial/` directory exists
- [x] `manifest.json` with all required fields
- [x] `__init__.py` with proper setup functions
- [x] Valid integration code

✅ **Documentation**
- [x] Professional README.md
- [x] Comprehensive changelog (CHANGELOG.md)
- [x] Code documentation and docstrings
- [x] Usage examples and guides

✅ **Code Quality**
- [x] No syntax errors
- [x] Follows Home Assistant conventions
- [x] Proper error handling
- [x] Professional code structure

✅ **Manifest Requirements**
- [x] Valid domain name
- [x] Proper issue tracker URL
- [x] Documentation URL
- [x] Codeowners specified
- [x] Version number
- [x] Quality scale declaration

✅ **GitHub Repository Settings**
- [ ] Issues enabled (needs to be done)
- [ ] Topics added (needs to be done)
- [x] Public repository
- [x] Proper repository name

## After Validation Passes

Once HACS validation passes, your integration will be eligible for:

1. **HACS Default Repository** - Consider submitting for inclusion
2. **Community Discovery** - Topics help users find your integration
3. **Professional Recognition** - Gold standard badge display
4. **Improved SEO** - Better search visibility

## Troubleshooting

### If Issues Still Persist

1. **Check Repository Name**: Ensure it matches manifest URLs
2. **Verify Topics**: Must include `home-assistant` and `hacs`
3. **Wait Time**: GitHub changes can take 5-15 minutes to propagate
4. **Repository Visibility**: Must be public repository

### Common Topic Mistakes

❌ **Don't use:**
- Spaces in single topic (`home assistant` instead of `home-assistant`)
- Too many topics (GitHub limits to reasonable number)
- Irrelevant topics (unrelated to functionality)

✅ **Do use:**
- Kebab-case for multi-word topics (`home-assistant`)
- Relevant, descriptive topics
- Standard Home Assistant ecosystem topics

## Contact

If validation still fails after following this guide:
- Check HACS documentation: https://hacs.xyz/docs/publish/
- File issue with HACS: https://github.com/hacs/integration
- Review other successful integrations for examples