@echo off
REM ==================================================================
REM  EduMentor Voice - Observability Stack Launcher (Windows)
REM
REM  Starts the Prometheus, Alertmanager, and Grafana containers.
REM ==================================================================

echo [EduMentor] Starting Prometheus, Alertmanager, and Grafana...
echo.

cd infra\observability

docker-compose up -d

echo.
echo [EduMentor] Observability stack started successfully!
echo.
echo Prometheus:   http://localhost:9090
echo Alertmanager: http://localhost:9093
echo Grafana:      http://localhost:3000
echo.
pause
