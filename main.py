import sys

if __name__ == "__main__":
    if len(sys.argv)==5 and sys.argv[1]=='--run-exercise':
        from netlab.exercise_runner import run_exercise
        raise SystemExit(run_exercise(*sys.argv[2:]))
    from netlab.app import main
    try:
        raise SystemExit(main())
    except Exception:
        import logging
        logging.getLogger('netlab').exception('Application startup failed')
        raise
