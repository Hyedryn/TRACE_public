
$(document).ready(function() {
    let profilesData = [];

    // Load settings when modal opens
    $('#settings-modal').on('show.bs.modal', function() {
        $.get("/api/settings", function(data) {
            $("#setting-max-duration").val(data.max_duration || 300);
            $("#setting-parser-method").val(data.parser_method || 'bs');
            $("#setting-persona-filter-enabled").prop('checked', data.persona_filter_enabled !== false);
            $("#setting-persona-filter-seconds").val(data.persona_filter_seconds || 60);
            $("#setting-persona-filter-transcript-seconds").val(data.persona_filter_transcript_seconds || 120);

            // Toggle persona filter settings visibility
            togglePersonaFilterSettings();
        }).fail(function() {
            alert("Error loading settings");
        });
    });

    // Toggle persona filter settings based on checkbox
    function togglePersonaFilterSettings() {
        if ($("#setting-persona-filter-enabled").is(':checked')) {
            $("#persona-filter-settings").show();
        } else {
            $("#persona-filter-settings").hide();
        }
    }

    $("#setting-persona-filter-enabled").change(togglePersonaFilterSettings);

    // Handle database viewer table selection
    $(document).on('click', '#table-list button', function() {
        const tableName = $(this).data('table');

        // Update active state
        $('#table-list button').removeClass('active');
        $(this).addClass('active');

        // Update selected table name
        $('#selected-table-name').text(tableName);

        // Fetch and display table data
        $.get(`/api/database/table/${tableName}`, function(response) {
            // Clear previous data
            $('#db-table-headers').empty();
            $('#db-table-body').empty();

            // Add headers
            response.columns.forEach(function(col) {
                $('#db-table-headers').append(`<th>${col}</th>`);
            });

            // Add rows
            if (response.data.length === 0) {
                $('#db-table-body').append(`
                    <tr>
                        <td colspan="${response.columns.length}" class="text-center text-muted">
                            No data in this table
                        </td>
                    </tr>
                `);
            } else {
                response.data.forEach(function(row) {
                    let rowHtml = '<tr>';
                    response.columns.forEach(function(col) {
                        let value = row[col];
                        // Truncate long values
                        if (value && typeof value === 'string' && value.length > 100) {
                            value = value.substring(0, 100) + '...';
                        }
                        rowHtml += `<td>${value !== null ? value : '<em class="text-muted">null</em>'}</td>`;
                    });
                    rowHtml += '</tr>';
                    $('#db-table-body').append(rowHtml);
                });
            }

            // Update row count
            $('#db-row-count').text(`Showing ${response.showing} of ${response.total_rows} total rows`);
        }).fail(function(xhr) {
            alert("Error loading table data: " + (xhr.responseJSON?.error || "Unknown error"));
        });
    });

    // Save settings
    $("#save-settings").click(function() {
        const settingsData = {
            max_duration: parseInt($("#setting-max-duration").val()),
            parser_method: $("#setting-parser-method").val(),
            persona_filter_enabled: $("#setting-persona-filter-enabled").is(':checked'),
            persona_filter_seconds: parseInt($("#setting-persona-filter-seconds").val()),
            persona_filter_transcript_seconds: parseInt($("#setting-persona-filter-transcript-seconds").val())
        };

        $.ajax({
            type: "POST",
            url: "/api/settings",
            data: JSON.stringify(settingsData),
            contentType: "application/json",
            success: function(response) {
                alert(response.message);
                $('#settings-modal').modal('hide');
            },
            error: function(xhr, status, error) {
                alert("Error saving settings: " + (xhr.responseJSON?.error || error));
            }
        });
    });

    // Load profiles and contexts on page load
    $.get("/api/profiles", function(data) {
        profilesData = data;
        data.forEach(function(profile) {
            $("#single-profile").append(`<option value="${profile.id}">${profile.name}</option>`);
        });
    });

    $.get("/api/contexts", function(data) {
        console.log("Contexts from API:", data);
        $("#contexts").empty();
        $("#contexts").append(`<option value="" disabled selected>Select a context...</option>`);
        data.forEach(function(context) {
            $("#contexts").append(`<option value="${context.id}">${context.name}</option>`);
        });
    });

    $("#experiment-mode").change(function() {
        const mode = $(this).val();

        // Reset all sections
        $("#num-personas-section").hide();
        $("#single-profile-section").hide();
        $("#multiple-personas-container").empty();

        if (mode === "random_choice") {
            // Hide entire profiles section for random choice
            $("#profiles-section").hide();
        } else if (mode === "single_persona") {
            // Show profiles section with single select
            $("#profiles-section").show();
            $("#single-profile-section").show();
        } else if (mode === "mixed_persona" || mode === "sequential_persona") {
            // Show profiles section with number input
            $("#profiles-section").show();
            $("#num-personas-section").show();
        }
    });

    // Initialize with default mode (single_persona)
    $("#experiment-mode").trigger("change");

    // Generate persona selectors
    $("#generate-persona-selectors").click(function() {
        const mode = $("#experiment-mode").val();
        const numPersonas = parseInt($("#num-personas").val());

        if (numPersonas < 1) {
            alert("Please enter a valid number of personas (minimum 1)");
            return;
        }

        $("#multiple-personas-container").empty();

        for (let i = 0; i < numPersonas; i++) {
            let selectorHtml = `
                <div class="persona-selector mb-3" data-index="${i}">
                    <label class="form-label">Persona ${i + 1}</label>
                    <div class="input-group">
                        <select class="form-select persona-select" data-index="${i}">
                            <option value="">Select a persona...</option>
            `;

            profilesData.forEach(function(profile) {
                selectorHtml += `<option value="${profile.id}">${profile.name}</option>`;
            });

            selectorHtml += `</select>`;

            if (mode === "mixed_persona") {
                selectorHtml += `
                    <span class="input-group-text">Weight</span>
                    <input type="number" class="form-control persona-weight" data-index="${i}" value="1" min="0" step="0.1">
                `;
            }

            if (mode === "sequential_persona") {
                selectorHtml += `
                    <span class="input-group-text">Steps</span>
                    <input type="number" class="form-control persona-steps" data-index="${i}" value="10" min="1" step="1">
                `;
            }

            selectorHtml += `</div></div>`;

            $("#multiple-personas-container").append(selectorHtml);
        }
    });

    // Handle experiment form submission
    $("#experiment-form").submit(function(event) {
        event.preventDefault();

        const mode = $("#experiment-mode").val();
        const experimentData = {
            mode: mode,
            profiles: [],
            context: $("#contexts").val(),
            max_depth: parseInt($("#max-depth").val()),
            concurrent_users: parseInt($("#concurrent-users").val()),
            weights: {},
            persona_sequence: []
        };

        // Collect profile data based on mode
        if (mode === "random_choice") {
            // No profiles needed
            experimentData.profiles = [];
        } else if (mode === "single_persona") {
            const selectedProfile = $("#single-profile").val();
            if (!selectedProfile) {
                alert("Please select a profile for single persona mode");
                return;
            }
            experimentData.profiles = [parseInt(selectedProfile)];
        } else if (mode === "mixed_persona") {
            // Collect from multiple persona selectors for mixed mode
            const personaSelects = $(".persona-select");

            if (personaSelects.length === 0) {
                alert("Please click 'Generate Selectors' to add personas");
                return;
            }

            let allSelected = true;
            personaSelects.each(function() {
                const value = $(this).val();
                if (!value) {
                    allSelected = false;
                    return false;
                }
                experimentData.profiles.push(parseInt(value));
            });

            if (!allSelected) {
                alert("Please select a persona for each slot");
                return;
            }

            // Collect weights for mixed persona
            $(".persona-weight").each(function(index) {
                const profileId = experimentData.profiles[index];
                experimentData.weights[profileId] = parseFloat($(this).val());
            });
        } else if (mode === "sequential_persona") {
            // Collect from multiple persona selectors for sequential mode
            const personaSelects = $(".persona-select");

            if (personaSelects.length === 0) {
                alert("Please click 'Generate Selectors' to add personas");
                return;
            }

            let allSelected = true;
            personaSelects.each(function(index) {
                const value = $(this).val();
                if (!value) {
                    allSelected = false;
                    return false;
                }

                const steps = parseInt($(".persona-steps[data-index='" + index + "']").val());
                experimentData.persona_sequence.push({
                    profile_id: parseInt(value),
                    steps: steps
                });
            });

            if (!allSelected) {
                alert("Please select a persona for each slot");
                return;
            }
        }

        $.ajax({
            type: "POST",
            url: "/api/start-experiment",
            data: JSON.stringify(experimentData),
            contentType: "application/json",
            success: function(response) {
                alert(response.message);
                updateStatus();
            },
            error: function(xhr, status, error) {
                alert("Error starting experiment: " + (xhr.responseJSON?.error || error));
            }
        });
    });

    // Update status periodically
    function updateStatus() {
        $.get("/api/status", function(data) {
            $("#experiment-status").empty();
            if (data.length === 0) {
                $("#experiment-status").append(`
                    <tr>
                        <td colspan="6" class="text-center text-muted">
                            <i class="bi bi-hourglass-split"></i> No experiments running
                        </td>
                    </tr>
                `);
            } else {
                data.forEach(function(experiment) {
                    let progress = (experiment.progress != null) ? `${experiment.progress}%` : 'N/A';
                    let phase = experiment.phase || 'N/A';
                    let statusBadge = '';
                    if (experiment.status === 'running') {
                        statusBadge = '<span class="badge bg-success"><i class="bi bi-play-fill"></i> Running</span>';
                    } else if (experiment.status === 'exited') {
                        statusBadge = '<span class="badge bg-secondary"><i class="bi bi-stop-fill"></i> Exited</span>';
                    } else {
                        statusBadge = `<span class="badge bg-info">${experiment.status}</span>`;
                    }

                    let actionButtons = '';
                    if (experiment.status === 'running') {
                        if (experiment.view_url) {
                            actionButtons += `<a href="${experiment.view_url}" target="_blank" class="btn btn-sm btn-primary me-1"><i class="bi bi-eye-fill"></i> Watch</a>`;
                        }
                        // Only show stop button for first user of multi-user experiment (stops whole container)
                        if (experiment.user_id === 1) {
                            actionButtons += `<button class="btn btn-sm btn-danger stop-experiment-btn" data-container="${experiment.container_name}"><i class="bi bi-stop-fill"></i> Stop</button>`;
                        }
                    }

                    $("#experiment-status").append(`
                        <tr>
                            <td><strong>${experiment.name}</strong></td>
                            <td><i class="bi bi-person-badge"></i> ${experiment.profiles}</td>
                            <td>${statusBadge}</td>
                            <td><span class="badge bg-info">${phase}</span></td>
                            <td>${progress}</td>
                            <td>${actionButtons}</td>
                        </tr>
                    `);
                });
            }
        });
    }

    setInterval(updateStatus, 5000); // Update every 5 seconds
    updateStatus();

    // Handle clear experiments button
    $("#clear-experiments-btn").click(function() {
        if (confirm("Are you sure you want to remove all exited experiments from the list?")) {
            $.ajax({
                type: "POST",
                url: "/api/clear-experiments",
                contentType: "application/json",
                success: function(response) {
                    alert(response.message);
                    updateStatus();
                },
                error: function(xhr, status, error) {
                    alert("Error clearing experiments: " + (xhr.responseJSON?.error || error));
                }
            });
        }
    });

    // Handle stop experiment button (using event delegation for dynamically added buttons)
    $(document).on('click', '.stop-experiment-btn', function() {
        const containerName = $(this).data('container');
        const experimentName = containerName.replace('scraper-', '');
        if (confirm(`Are you sure you want to stop experiment '${experimentName}'? This will stop all concurrent users.`)) {
            $.ajax({
                type: "POST",
                url: `/api/stop-experiment/${experimentName}`,
                contentType: "application/json",
                success: function(response) {
                    alert(response.message);
                    updateStatus();
                },
                error: function(xhr, status, error) {
                    alert("Error stopping experiment: " + (xhr.responseJSON?.error || error));
                }
            });
        }
    });

    // Handle add persona form submission
    $("#save-persona").click(function() {
        const personaData = {
            name: $("#persona-name").val(),
            description: $("#persona-description").val()
        };

        $.ajax({
            type: "POST",
            url: "/api/add-profile",
            data: JSON.stringify(personaData),
            contentType: "application/json",
            success: function(response) {
                alert(response.message);
                $('#add-persona-modal').modal('hide');
                // Clear and refresh profiles list
                $("#single-profile").empty();
                $.get("/api/profiles", function(data) {
                    profilesData = data;
                    data.forEach(function(profile) {
                        $("#single-profile").append(`<option value="${profile.id}">${profile.name}</option>`);
                    });
                });
            }
        });
    });

    // Handle add context form submission
    $(document).on("click", "#save-context", function() {
        console.log("Save context button clicked");
        const contextData = {
            name: $("#context-name").val(),
            description: $("#context-description").val(),
            videos: $("#context-videos").val()
        };
        console.log("Context data:", contextData);

        $.ajax({
            type: "POST",
            url: "/api/add-context",
            data: JSON.stringify(contextData),
            contentType: "application/json",
            success: function(response) {
                alert(response.message);
                $('#add-context-modal').modal('hide');
                // Clear and refresh contexts list
                $("#contexts").empty();
                $("#contexts").append(`<option value="" disabled selected>Select a context...</option>`);
                $.get("/api/contexts", function(data) {
                    data.forEach(function(context) {
                        $("#contexts").append(`<option value="${context.id}">${context.name}</option>`);
                    });
                });
            }
        });
    });
});
