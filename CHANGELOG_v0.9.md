# v0.9
- Removed the thumbnail Edit action and removed the local Thumbnail Studio implementation.
- Removed the results-per-batch selector and manual next-batch button. The gallery auto-loads more results as the user scrolls; internal fetch batches are 20.
- Added minimum video duration presets (30, 40, 50 minutes+) and a custom 30–360 minute setting, persisted in local configuration.
- Replaced the misleading actor-image mode with Similar Thumbnail Image mode.
- Similar-thumbnail mode compares selected reference images with popular YouTube thumbnail candidates locally using OpenCV color histograms and difference hash; it displays a heuristic similarity percentage.
- Actor, topic, and image modes all sort matching results by views descending.
- Download all shown now downloads every currently visible gallery result.
- Documented that image search is bounded and heuristic, not internet-wide reverse image search or face recognition.
