# Workspace Rules & Development Flow

To ensure smooth deployments to the development and production servers, follow this systematic workflow for all new cases and feature requests:

1. **Pull Latest Changes**:
   - Always run `git pull` at the start of any new session or case to synchronize the local workspace with the remote repository.
   
2. **Analysis & Implementation**:
   - Analyze requirements and apply design systems using vanilla CSS/HTML.
   - Run verification checks locally.
   
3. **Commit & Push**:
   - When implementation is verified, stage and commit the changes using clear commit messages.
   - Run `git push` to upload the commits/tags to the remote repository. This ensures that the server deployment scripts (`deploy.sh`) can successfully fetch the updates.
